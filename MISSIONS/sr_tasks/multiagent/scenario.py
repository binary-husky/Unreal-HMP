import numpy as np
import importlib
# defines scenario upon which the world is built
class BaseScenario(object):
    # create elements of the world
    def make_world(self):
        raise NotImplementedError()
    # create initial conditions of the world
    def reset_world(self, world):
        raise NotImplementedError()

def sr_tasks_env(env_id, rank):
    import multiagent.scenarios as scenarios
    from multiagent.environment import MultiAgentEnv
    Scenario = getattr(importlib.import_module('MISSIONS.sr_tasks.multiagent.scenarios.'+env_id), 'Scenario')
    scenario = Scenario(process_id=rank)
    world = scenario.make_world()
    env = MultiAgentEnv(world=world,
                        reset_callback=scenario.reset_world,
                        reward_callback=scenario.reward,
                        observation_callback=scenario.observation,
                        info_callback=scenario.info if hasattr(scenario, 'info') else None,
                        discrete_action=True,
                        done_callback=scenario.done)
    return env