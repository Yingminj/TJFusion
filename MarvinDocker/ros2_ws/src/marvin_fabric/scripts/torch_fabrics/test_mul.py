import torch
batch = 5
task_dim = 1
nv = 14

J_flat = torch.randn(batch, task_dim, nv)
M_diag = torch.eye(task_dim).repeat(batch, 1, 1)  # 每个任务一个 3x3 metric

J_T = J_flat.transpose(1, 2)
M_r_batch = torch.bmm(J_T, torch.bmm(M_diag, J_flat))
M_r = M_r_batch.sum(dim=0)

print(M_r.shape)  # ✅ torch.Size([14, 14])
