from __future__ import annotations

from typing import Any, List, Dict, Tuple, Set

import pickle
from pathlib import Path

from stable_baselines3.common.type_aliases import MaybeCallback
from stable_baselines3.common.utils import constant_fn
from stable_baselines3.sac.sac import SAC

from autorl_landscape.custom_agents.off_policy_algorithm import custom_learn
from autorl_landscape.run.rl_context import make_env_mygym, seed_rl_context

import torch
import os


class CustomSAC(SAC):
    """Slightly changed SAC Agent that can be saved and loaded at any point to reproduce learning exactly."""

    def learn(
        self,
        total_timesteps: int,
        callback: MaybeCallback = None,
        log_interval: int = 4,
        tb_log_name: str = "SAC",
        reset_num_timesteps: bool = True,
        progress_bar: bool = False,
    ) -> CustomSAC:
        """Like original method from `OffPolicyAlgorithm`, but call `after_update()` callback method."""
        return custom_learn(
            self, total_timesteps, callback, log_interval, tb_log_name, reset_num_timesteps, progress_bar
        )

    @classmethod
    def custom_load_mygym(cls, save_path: Path, arg_dict, seed: int) -> CustomSAC:
        """Load agent which will perform deterministically with further training, like the originally saved agent."""
        # load model stay the same
        # restore state in pybullet
        loaded_agent: CustomSAC = CustomSAC.load(save_path / Path("model.zip"))
        loaded_agent.load_replay_buffer(save_path / Path("replay_buffer.pkl"))
        env = make_env_mygym('Gym-v0', seed, n_envs=None, arg_dict=arg_dict)
        loaded_agent.set_env(env, force_reset=True)
        seed_rl_context(loaded_agent, seed)
        return loaded_agent
    
    @classmethod
    def custom_load(cls, save_path: Path, seed: int) -> CustomSAC:
        """Load agent which will perform deterministically with further training, like the originally saved agent."""
        loaded_agent: CustomSAC = CustomSAC.load(save_path / Path("model.zip"))
        loaded_agent.load_replay_buffer(save_path / Path("replay_buffer.pkl"))
        with open(save_path / Path("env.pkl"), "rb") as f:
            env, env_state = pickle.load(f)
            loaded_agent.set_env(env, force_reset=False)
            loaded_agent.env.envs[0].sim.set_state(env_state)
        seed_rl_context(loaded_agent, seed)
        return loaded_agent

    def custom_save_mygym(self, save_path: Path, seed: int) -> None:
        """Save the agent so that it will perform deterministically with further training.

        Can be loaded afterwards with `custom_load`.
        """
        # re-seed the original agent to allow for same results with the loaded agent
        # save model also by torch mode
        # save state in pybullet 
        seed_rl_context(self, seed)

        self.save(f"{save_path}/model.zip")
        current_path = os.getcwd()
        model_path = os.path.join(current_path, save_path, "model.pth.tar")
        torch.save(self.get_parameters(), f"{save_path}/model.pth.tar", _use_new_zipfile_serialization=False)
        self.save_replay_buffer(f"{save_path}/replay_buffer.pkl")
        # with open(f"{save_path}/env.pkl", "wb") as f:
        #     env = self.get_env()
        #     # https://github.com/openai/gym/issues/402#issuecomment-482573989
        #     env_state = self.env.envs[0].p.saveState()
        #     pickle.dump((env, env_state), f)

    def custom_save(self, save_path: Path, seed: int) -> None:
        """Save the agent so that it will perform deterministically with further training.

        Can be loaded afterwards with `custom_load`.
        """
        # re-seed the original agent to allow for same results with the loaded agent
        seed_rl_context(self, seed)

        self.save(f"{save_path}/model.zip")
        self.save_replay_buffer(f"{save_path}/replay_buffer.pkl")
        with open(f"{save_path}/env.pkl", "wb") as f:
            env = self.get_env()
            # https://github.com/openai/gym/issues/402#issuecomment-482573989
            env_state = self.env.envs[0].sim.get_state()
            pickle.dump((env, env_state), f)

    def set_ls_conf(self, ls_spec: Dict[str, Any], _: int) -> None:
        """Set up the agent with the wanted configuration. Special handling for learning rate."""
        for hp_name, hp_val in ls_spec.items():
            # First, handle special cases:
            if hp_name == "learning_rate":
                    self.lr_schedule = constant_fn(hp_val)
                # Then, the rest:
            else:
                    if not hasattr(self, hp_name):
                        error_msg = f"Hyperparameter {hp_name} cannot be set for {type(self)}."
                        raise ValueError(error_msg)
                    setattr(self, hp_name, hp_val)

    def get_ls_conf(self, ls_spec: List[str]) -> Dict[str, Any]:
        """Read the actually used hyperparameter configuration.

        Args:
            ls_spec: list of hyperparameters to read (should come from the hydra config)
        """
        ls_conf: Dict[str, Any] = {}
        for hp_name in ls_spec:
            if hp_name == "learning_rate":
                    ls_conf["learning_rate"] = self.lr_schedule(self._current_progress_remaining)
            else:
                    if not hasattr(self, hp_name):
                        error_msg = f"Hyperparameter {hp_name} does not exist for {type(self)}."
                        raise ValueError(error_msg)
                    ls_conf[hp_name] = getattr(self, hp_name)
        return ls_conf
