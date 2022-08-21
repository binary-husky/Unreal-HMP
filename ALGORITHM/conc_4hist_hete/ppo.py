import torch, math, traceback
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
from random import randint, sample
from torch.utils.data.sampler import BatchSampler, SubsetRandomSampler
from UTIL.colorful import *
from UTIL.tensor_ops import _2tensor, __hash__, repeat_at
from config import GlobalConfig as cfg
from UTIL.gpu_share import GpuShareUnit
from .ppo_sampler import TrajPoolSampler

class PPO():
    def __init__(self, policy_and_critic, ppo_config, mcv=None):
        self.policy_and_critic = policy_and_critic
        self.clip_param = ppo_config.clip_param
        self.ppo_epoch = ppo_config.ppo_epoch
        self.n_pieces_batch_division = ppo_config.n_pieces_batch_division
        self.value_loss_coef = ppo_config.value_loss_coef
        self.entropy_coef = ppo_config.entropy_coef
        self.max_grad_norm = ppo_config.max_grad_norm
        self.add_prob_loss = ppo_config.add_prob_loss
        self.prevent_batchsize_oom = ppo_config.prevent_batchsize_oom
        # self.freeze_body = ppo_config.freeze_body
        self.lr = ppo_config.lr
        self.all_parameter = list(policy_and_critic.named_parameters())
        self.at_parameter = [(p_name, p) for p_name, p in self.all_parameter if 'AT_' in p_name]
        self.ct_parameter = [(p_name, p) for p_name, p in self.all_parameter if 'CT_' in p_name]
        # self.ae_parameter = [(p_name, p) for p_name, p in self.all_parameter if 'AE_' in p_name]
        # 检查剩下是是否全都是不需要训练的参数
        remove_exists = lambda LA,LB: list(set(LA).difference(set(LB)))
        res = self.all_parameter
        res = remove_exists(res, self.at_parameter)
        res = remove_exists(res, self.ct_parameter)
        # res = remove_exists(res, self.ae_parameter)
        for p_name, p in res:   
            assert not p.requires_grad, ('a parameter must belong to either CriTic or AcTor, unclassified parameter:',p_name)

        self.cross_parameter = [(p_name, p) for p_name, p in self.all_parameter if ('CT_' in p_name) and ('AT_' in p_name)]
        assert len(self.cross_parameter)==0,('a parameter must belong to either CriTic or AcTor, not both')


        # if not self.freeze_body:
        self.at_parameter = [p for p_name, p in self.all_parameter if 'AT_' in p_name]
        self.at_optimizer = optim.Adam(self.at_parameter, lr=self.lr)

        self.ct_parameter = [p for p_name, p in self.all_parameter if 'CT_' in p_name]
        self.ct_optimizer = optim.Adam(self.ct_parameter, lr=self.lr*10.0) #(self.lr)
        # else:
        #     self.at_parameter = [p for p_name, p in self.all_parameter if 'AT_div_tree' in p_name]
        #     self.at_optimizer = optim.Adam(self.at_parameter, lr=self.lr)
        #     self.ct_parameter = [p for p_name, p in self.all_parameter if 'CT_' in p_name]
        #     self.ct_optimizer = optim.Adam(self.ct_parameter, lr=self.lr*10.0) #(self.lr)

        self.g_update_delayer = 0
        self.g_initial_value_loss = 0
        # 轮流训练式
        self.mcv = mcv
        self.ppo_update_cnt = 0
        self.batch_size_reminder = True
        self.trivial_dict = {}

        assert self.n_pieces_batch_division == 1
        self.n_div = 1
        # print亮红(self.n_div)

        self.gpu_share_unit = GpuShareUnit(cfg.device, gpu_party=cfg.gpu_party)

    def freeze_body(self):
        self.freeze_body = True
        self.at_parameter = [p for p_name, p in self.all_parameter if 'AT_policy_head' in p_name]
        self.at_optimizer = optim.Adam(self.at_parameter, lr=self.lr)
        self.ct_parameter = [p for p_name, p in self.all_parameter if 'CT_' in p_name]
        self.ct_optimizer = optim.Adam(self.ct_parameter, lr=self.lr*10.0) #(self.lr)
        print('change train object')

    def train_on_traj(self, traj_pool, task):
        while True:
            try:
                with self.gpu_share_unit:
                    self.train_on_traj_(traj_pool, task) 
                break # 运行到这说明显存充足
            except RuntimeError as err:
                print(traceback.format_exc())
                if self.prevent_batchsize_oom:
                    # in some cases, reversing MaxSampleNum a single time is not enough
                    # [ 10, 20, 30, 40] 
                    # --> inversion 1
                    # [ 10, 20, 30, -1], try 30
                    if TrajPoolSampler.MaxSampleNum[-1] < 0: TrajPoolSampler.MaxSampleNum.pop(-1)
                    assert TrajPoolSampler.MaxSampleNum[-1] > 0
                    # -> [ 10, 20, 30]
                    TrajPoolSampler.MaxSampleNum[-1] = -1
                    # -> [ 10, 20, -1], try 20
                    print亮红('显存不足！ 回溯上次的样本量')
                else:
                    self.n_div += 1
                    print亮红('显存不足！ 切分样本, 当前n_div: %d'%self.n_div)
            torch.cuda.empty_cache()

    def train_on_traj_(self, traj_pool, task):

        ppo_valid_percent_list = []
        sampler = TrajPoolSampler(n_div=self.n_div, traj_pool=traj_pool, flag=task, prevent_batchsize_oom=self.prevent_batchsize_oom)
        assert self.n_div == len(sampler)
        for e in range(self.ppo_epoch):
            # print亮紫('pulse')
            sample_iter = sampler.reset_and_get_iter()
            self.at_optimizer.zero_grad()
            self.ct_optimizer.zero_grad()
            for i in range(self.n_div):
                # ! get traj fragment
                sample = next(sample_iter)
                # ! build graph, then update network
                loss_final, others = self.establish_pytorch_graph(task, sample, e)
                loss_final = loss_final*0.5 /self.n_div
                if (e+i)==0: print('[PPO.py] Memory Allocated %.2f GB'%(torch.cuda.memory_allocated()/1073741824))
                loss_final.backward()
                # log
                ppo_valid_percent_list.append(others.pop('PPO valid percent').item())
                self.log_trivial(dictionary=others); others = None
            nn.utils.clip_grad_norm_(self.at_parameter, self.max_grad_norm)
            self.at_optimizer.step()
            self.ct_optimizer.step()
            if ppo_valid_percent_list[-1] < 0.70: 
                print亮黄('policy change too much, epoch terminate early'); break
        pass # finish all epoch update

        print亮黄(np.array(ppo_valid_percent_list))
        self.log_trivial_finalize()
        # print亮红('Leaky Memory Allocated %.2f GB'%(torch.cuda.memory_allocated()/1073741824))

        self.ppo_update_cnt += 1
        return self.ppo_update_cnt

    def log_trivial(self, dictionary):
        for key in dictionary:
            if key not in self.trivial_dict: self.trivial_dict[key] = []
            item = dictionary[key].item() if hasattr(dictionary[key], 'item') else dictionary[key]
            self.trivial_dict[key].append(item)

    def log_trivial_finalize(self, print=True):
        for key in self.trivial_dict:
            self.trivial_dict[key] = np.array(self.trivial_dict[key])
        
        print_buf = ['[ppo.py] ']
        for key in self.trivial_dict:
            self.trivial_dict[key] = self.trivial_dict[key].mean()
            print_buf.append(' %s:%.3f, '%(key, self.trivial_dict[key]))
            if self.mcv is not None:  self.mcv.rec(self.trivial_dict[key], key)
        if print: print紫(''.join(print_buf))
        if self.mcv is not None:
            self.mcv.rec_show()
        self.trivial_dict = {}


    def establish_pytorch_graph(self, flag, sample, n):
        obs = _2tensor(sample['obs'])
        advantage = _2tensor(sample['advantage'])
        action = _2tensor(sample['action'])
        oldPi_actionLogProb = _2tensor(sample['actionLogProb'])
        real_value = _2tensor(sample['return'])
        real_threat = _2tensor(sample['threat'])
        hete_pick = _2tensor(sample['hete_pick'])
        avail_act = _2tensor(sample['avail_act']) if 'avail_act' in sample else None

        batchsize = advantage.shape[0]#; print亮紫(batchsize)
        batch_agent_size = advantage.shape[0]*advantage.shape[1]

        assert flag == 'train'
        newPi_value, newPi_actionLogProb, entropy, probs, others = \
            self.policy_and_critic.evaluate_actions(obs=obs, eval_actions=action, test_mode=False, avail_act=avail_act, hete_pick=hete_pick)
        entropy_loss = entropy.mean()


        # threat approximation
        SAFE_LIMIT = 11
        filter = (real_threat<SAFE_LIMIT) & (real_threat>=0)
        threat_loss = F.mse_loss(others['threat'][filter], real_threat[filter])

        n_actions = probs.shape[-1]
        if self.add_prob_loss: assert n_actions <= 15  # 
        penalty_prob_line = (1/n_actions)*0.12
        probs_loss = (penalty_prob_line - torch.clamp(probs, min=0, max=penalty_prob_line)).mean()
        if not self.add_prob_loss:
            probs_loss = torch.zeros_like(probs_loss)

        # dual clip ppo core
        E = newPi_actionLogProb - oldPi_actionLogProb
        E_clip = torch.zeros_like(E)
        E_clip = torch.where(advantage > 0, torch.clamp(E, max=np.log(1.0+self.clip_param)), E_clip)
        E_clip = torch.where(advantage < 0, torch.clamp(E, min=np.log(1.0-self.clip_param), max=np.log(5) ), E_clip)
        ratio = torch.exp(E_clip)
        policy_loss = -(ratio*advantage).mean()

        # add all loses
        value_loss = 0.5 * F.mse_loss(real_value, newPi_value)
        if 'motivation value' in others:
            value_loss += 0.5 * F.mse_loss(real_value, others['motivation value'])

        AT_net_loss = policy_loss - entropy_loss*self.entropy_coef # + probs_loss*20
        CT_net_loss = value_loss * 1.0 + threat_loss * 0.1 # + friend_threat_loss*0.01
        # AE_new_loss = ae_loss * 1.0

        loss_final =  AT_net_loss + CT_net_loss  # + AE_new_loss

        ppo_valid_percent = ((E_clip == E).int().sum()/batch_agent_size)

        nz_mask = real_value!=0
        value_loss_abs = (real_value[nz_mask] - newPi_value[nz_mask]).abs().mean()
        others = {
            # 'Policy loss':              policy_loss,
            # 'Entropy loss':             entropy_loss,
            'Value loss Abs':           value_loss_abs,
            # 'friend_threat_loss':       friend_threat_loss,
            'PPO valid percent':        ppo_valid_percent,
            'threat loss':              threat_loss,
            # 'Auto encoder loss':        ae_loss,
            'CT_net_loss':              CT_net_loss,
            'AT_net_loss':              AT_net_loss,
        }


        return loss_final, others

