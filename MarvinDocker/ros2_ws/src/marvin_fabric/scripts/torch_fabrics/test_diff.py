import torch
from functorch import jacfwd

class Env:
    def __init__(self):
        self.obs_radii = torch.tensor([0.4, 0.6, 0.8])

    def obstacle_avoidance_task_map(self, x: torch.Tensor, obs_pos: torch.Tensor):
        """
        x: (3,)
        obs_pos: (n,3)
        output: (n,)
        """
        diff = x[None, :] - obs_pos           # (n,3)
        eps = 1e-6
        norms = torch.sqrt(torch.sum(diff ** 2, dim=1) + eps)  # (n,)

        # 半径和广播
        radii = 0.5 * self.obs_radii          # (n,)
        normed = norms / radii - 1            # (n,)

        return normed.double()

env = Env()
x = torch.tensor([1.0, 2.0, 3.0], requires_grad=True)
obs_pos = torch.tensor([
    [1.5, 2.0, 3.0],
    [0.0, 2.5, 4.0],
    [1.0, 1.0, 2.0]
])

# 使用 partial 固定 obs_pos
from functools import partial
J = jacfwd(partial(env.obstacle_avoidance_task_map, obs_pos=obs_pos))(x)
print(J)
print(J.shape)
