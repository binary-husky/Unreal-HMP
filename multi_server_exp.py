
# ubuntu command to kill process: kill -9 $(ps -ef | grep StarCraft | grep fuqingxu | grep -v grep | awk '{print $ 2}')
# ubuntu command to kill process: kill -9 $(ps -ef | grep python | grep fuqingxu | grep -v grep | awk '{print $ 2}')

n_run = 6
n_run_mode = [
    {
        "addr": "172.18.116.150:2233",
        "usr": "fuqingxu",
        "pwd": "clara"
    },
    {
        "addr": "172.18.116.150:2233",
        "usr": "fuqingxu",
        "pwd": "clara"
    },    
    {
        "addr": "172.18.116.150:2233",
        "usr": "fuqingxu",
        "pwd": "clara"
    },    
    {
        "addr": "172.18.116.150:2233",
        "usr": "fuqingxu",
        "pwd": "clara"
    },
    {
        "addr": "172.18.116.150:2233",
        "usr": "fuqingxu",
        "pwd": "clara"
    },
    {
        "addr": "172.18.116.150:2233",
        "usr": "fuqingxu",
        "pwd": "clara"
    },

]
assert len(n_run_mode)==n_run

conf_override = {
    "config.py->GlobalConfig-->note":       
                [
                    "apex_run1",  "apex_run2", "apex_run3",  
                    "normal_run4",  "normal_run5", "normal_run6",  
                ],

    "config.py->GlobalConfig-->seed":       
                [
                    8746186, 727287, 2727274, 
                    8746186, 727287, 2727274, 
                ],

    "ALGORITHM.conc.foundation.py->AlgorithmConfig-->lr":
                [
                    5e-4, 5e-4, 5e-4,
                    5e-4, 5e-4, 5e-4
                ],

    "ALGORITHM.conc.foundation.py->AlgorithmConfig-->experimental_useApex":       
                [
                    True, True, True, 
                    False, False, False, 
                ],

    "config.py->GlobalConfig-->device":       
                [
                    "cuda:0","cuda:2",
                    "cuda:3","cuda:4",
                    "cuda:5","cuda:6",
                ],

    "config.py->GlobalConfig-->gpu_party":       
                [
                    "off","off",
                    "off","off",
                    "off","off",
                ],
}



base_conf = {
    "config.py->GlobalConfig": {
        "note": "train_origin_T_R3",
        "env_name":"collective_assult",
        "env_path":"MISSIONS.collective_assult",
        "draw_mode": "Img",
        "num_threads": "64",
        "report_reward_interval": "64",
        "test_interval": "2048",
        "device": "cuda:0",
        "gpu_party": "Cuda0Party0",
        "gpu_fraction": 0.7,
        "fold": "1",
        "seed": 2022,
        "backup_files":[
            "ALGORITHM/conc",
            "MISSIONS/collective_assult"
        ]
    },

    "MISSIONS.collective_assult.collective_assult_parallel_run.py->ScenarioConfig": {
        "size": "5",
        "random_jam_prob": 0.05,
        "introduce_terrain":"True",
        "terrain_parameters": [0.05, 0.2],
        "num_steps": "180",
        "render":"False",
        "half_death_reward": "True",
        "TEAM_NAMES": [
            "ALGORITHM.conc.foundation->ReinforceAlgorithmFoundation"
        ]
    },

    "ALGORITHM.conc.foundation.py->AlgorithmConfig": {
        "n_focus_on": 2,               
        "actor_attn_mod": "False",     
        "lr": 5e-4,                  
        "ppo_epoch": 24,               
        "train_traj_needed": "64",     
        "load_checkpoint": "False",
        "experimental_rmDeadSample": "False",
        "experimental_useApex": "True",
    }
}

##############################################################################
##############################################################################
##############################################################################

import subprocess
import threading
import copy, os
import time
import json
from UTILS.colorful import *
arg_base = ['python', 'main.py']
time_mark = time.strftime("%Y-%m-%d-%H:%M:%S", time.localtime())
log_dir = '%s/'%time_mark
exp_log_dir = log_dir+'exp_log'
if not os.path.exists('PROFILE/%s'%exp_log_dir):
    os.makedirs('PROFILE/%s'%exp_log_dir)
exp_json_dir = log_dir+'exp_json'
if not os.path.exists('PROFILE/%s'%exp_json_dir):
    os.makedirs('PROFILE/%s'%exp_json_dir)

conf_list = []
new_json_paths = []
for i in range(n_run):
    conf = copy.deepcopy(base_conf)
    new_json_path = 'PROFILE/%s/run-%d.json'%(exp_json_dir, i+1)
    for key in conf_override:
        assert n_run == len(conf_override[key]), ('检查！n_run是否对应')
        tree_path, item = key.split('-->')
        conf[tree_path][item] = conf_override[key][i]
    with open(new_json_path,'w') as f:
        json.dump(conf, f, indent=4)
    # print(conf)
    conf_list.append(conf)
    new_json_paths.append(new_json_path)

print红('\n')
print红('\n')
print红('\n')

printX = [print亮红,print亮绿,print亮黄,print亮蓝,print亮紫,print亮靛, print红,print绿,print黄,print蓝,print紫,print靛,]
conf_base_ = conf_list[0]
for k_ in conf_base_:
    conf_base = conf_base_[k_]
    for key in conf_base:
        different = False
        for i in range(len(conf_list)):
            if conf_base[key]!=conf_list[i][k_][key]:
                different = True
                break
        # 
        if different:
            for i in range(len(conf_list)):
                printX[i](key, conf_list[i][k_][key])
        else:
            print(key, conf_base[key])



final_arg_list = []

for ith_run in range(n_run):
    final_arg = copy.deepcopy(arg_base)
    final_arg.append('--cfg')
    final_arg.append(new_json_paths[ith_run])
    final_arg_list.append(final_arg)
    print('')


def local_worker(ith_run):
    log_path = open('PROFILE/%s/run-%d.log'%(exp_log_dir, ith_run+1), 'w+')
    printX[ith_run%len(printX)](final_arg_list[ith_run])
    subprocess.run(final_arg_list[ith_run], stdout=log_path, stderr=log_path)

def remote_worker(ith_run):
    # step 1: transfer all files
    from UTILS.exp_upload import get_ssh_sftp
    
    addr = n_run_mode[ith_run]['addr']
    usr = n_run_mode[ith_run]['usr']
    pwd = n_run_mode[ith_run]['pwd']
    ssh, sftp = get_ssh_sftp(addr, usr, pwd)
    sftp.mkdir('/home/%s/MultiServerMission'%(usr), ignore_existing=True)
    sftp.mkdir('/home/%s/MultiServerMission/%s'%(usr, time_mark), ignore_existing=True)
    src_path = '/home/%s/MultiServerMission/%s/src'%(usr, time_mark)
    try:
        sftp.mkdir(src_path, ignore_existing=False)
        sftp.put_dir('./', src_path, ignore_list=['.vscode', '__pycache__','RECYCLE','ZHECKPOINT'])
        sftp.close()
        print紫('upload complete')
    except:
        sftp.close()
        print紫('do not need upload')

    time_mark_ = time_mark.replace(':','-')
    print('byobu attach -t %s'%time_mark_)

    stdin, stdout, stderr = ssh.exec_command(command='byobu new-session -d -s %s'%time_mark_, timeout=1)
    print亮紫('byobu new-session -d -s %s'%time_mark_)
    time.sleep(1)

    byobu_win_name = '%s--run-%d'%(time_mark_, ith_run)
    byobu_win_name = byobu_win_name.replace(':','-')
    stdin, stdout, stderr = ssh.exec_command(command='byobu new-window -t %s'%time_mark_, timeout=1)
    print亮紫('byobu new-window -t %s'%time_mark_)
    time.sleep(1)


    cmd = 'cd  ' + src_path
    stdin, stdout, stderr = ssh.exec_command(command='byobu send-keys -t %s "%s" C-m'%(time_mark_, cmd), timeout=1)
    print亮紫('byobu send-keys "%s" C-m'%cmd)
    time.sleep(1)

    cmd = ' '.join(final_arg_list[ith_run])
    stdin, stdout, stderr = ssh.exec_command(command='byobu send-keys -t %s "%s" C-m'%(time_mark_, cmd), timeout=1)
    print亮紫('byobu send-keys "%s" C-m'%cmd)
    time.sleep(1)

    # 杀死
    # stdin, stdout, stderr = ssh.exec_command(command='byobu kill-session -t %s'%byobu_win_name, timeout=1)
    pass

def worker(ith_run):
    if n_run_mode[ith_run] is None: 
        local_worker(ith_run)
    else:
        remote_worker(ith_run)



def clean_process(pid):
    import psutil
    parent = psutil.Process(pid)
    for child in parent.children(recursive=True):
        try:
            print亮红('sending Terminate signal to', child)
            child.terminate()
            time.sleep(5)
            print亮红('sending Kill signal to', child)
            child.kill()
        except: pass
    parent.kill()

def clean_up():
    print亮红('clean up!')
    parent_pid = os.getpid()   # my example
    clean_process(parent_pid)

DELAY = 10

if __name__ == '__main__':
        
    input('Confirm execution? 确认执行?')
    input('Confirm execution! 确认执行!')

    t = 0
    while (t >= 0):
        print('Counting down ', t)
        time.sleep(1)
        t -= 1

    for ith_run in range(n_run):
        worker(ith_run)
        for i in range(DELAY):
            time.sleep(1)

    print('all submitted')