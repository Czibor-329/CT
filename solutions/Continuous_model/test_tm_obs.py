"""Verification script for TM observation with wafer destination one-hot."""
from solutions.Continuous_model.env_single import Env_PN_Single

# single mode: TM=8
env_s = Env_PN_Single(device_mode="single", seed=0)
td_s = env_s.reset()
obs_s = td_s["observation"]
expected_s = env_s.net.get_obs_dim()
assert obs_s.shape[-1] == expected_s
print("single OK, obs_dim =", expected_s)

# cascade mode: TM=14
env_c = Env_PN_Single(device_mode="cascade", seed=0)
td_c = env_c.reset()
obs_c = td_c["observation"]
expected_c = env_c.net.get_obs_dim()
assert obs_c.shape[-1] == expected_c
print("cascade OK, obs_dim =", expected_c)
print("all checks passed")
