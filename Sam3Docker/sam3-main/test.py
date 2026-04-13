import torch
import time  # 引入时间模块
from PIL import Image
from sam3.model_builder import build_sam3_image_model
from sam3.model.sam3_image_processor import Sam3Processor
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# ==========================================
# 1. 模型初始化与计时
# ==========================================
print("正在加载 SAM3 模型，请稍候...")
start_load_time = time.time()

model = build_sam3_image_model(
    checkpoint_path="/home/yang/.cache/modelscope/hub/models/facebook/sam3/sam3.pt", # 请替换为实际的权重文件名
    load_from_HF=False,
    enable_segmentation=True
)
processor = Sam3Processor(model)

end_load_time = time.time()
print(f"✅ 模型加载完成！耗时: {end_load_time - start_load_time:.2f} 秒\n")

# ==========================================
# 2. 图像特征提取与计时 (只执行一次)
# ==========================================
image = Image.open("test.jpg")

print("正在提取图像全局特征 (Image Embedding)...")
start_embed_time = time.time()

inference_state = processor.set_image(image)

end_embed_time = time.time()
print(f"✅ 图像特征提取完成！耗时: {end_embed_time - start_embed_time:.3f} 秒\n")

# ==========================================
# 3. 可视化辅助函数
# ==========================================
def show_mask(mask, ax, color=None):
    if color is None:
        color = np.concatenate([np.random.random(3), np.array([0.6])], axis=0)
    else:
        color = np.array(list(color) + [0.6])
    h, w = mask.shape[-2:]
    mask_image = mask.reshape(h, w, 1) * color.reshape(1, 1, -1)
    ax.imshow(mask_image)

def show_box(box, score, label, ax):
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    rect = patches.Rectangle((x1, y1), w, h, linewidth=2, edgecolor='green', facecolor='none')
    ax.add_patch(rect)
    ax.text(x1, y1 - 5, f'{label}: {score:.2f}', fontsize=12, color='white', backgroundcolor='green')

# ==========================================
# 4. 设置交互式画布
# ==========================================
plt.ion()
fig, ax = plt.subplots(figsize=(10, 8))
image_np = np.array(image)
ax.imshow(image_np)
plt.axis('off')
plt.tight_layout()

plt.show(block=False) 
fig.canvas.draw()
fig.canvas.flush_events()

# ==========================================
# 5. 控制台交互循环 (包含提示词推理计时)
# ==========================================
confidence_threshold = 0.4
color_idx = 0
cmap = plt.cm.get_cmap("tab20", 20)

print("="*50)
print("SAM3 交互模式已启动！")
print("请在下方输入你想要分割的物体名称 (例如: red cup)。")
print("输入 'q', 'quit' 或 'exit' 退出程序。")
print("="*50 + "\n")

while True:
    prompt = input("请输入提示词 (Prompt): >>> ")
    
    if prompt.lower() in ['q', 'quit', 'exit']:
        print("退出交互模式。")
        break
        
    if not prompt.strip():
        continue

    # --- 开始提示词推理计时 ---
    start_prompt_time = time.time()
    
    output = processor.set_text_prompt(state=inference_state, prompt=prompt)
    
    end_prompt_time = time.time()
    prompt_duration = end_prompt_time - start_prompt_time
    # --- 结束提示词推理计时 ---
    
    masks_np = output["masks"].cpu().numpy()
    boxes_np = output["boxes"].cpu().numpy()
    scores_np = output["scores"].cpu().numpy()
    
    found = False
    for i in range(len(scores_np)):
        if scores_np[i] > confidence_threshold:
            found = True
            box = boxes_np[i]
            score = scores_np[i]
            mask = masks_np[i].squeeze()
            
            instance_color = cmap(color_idx % 20)[:3]
            color_idx += 1

            show_mask(mask, ax, color=instance_color)
            show_box(box, score, prompt, ax)
            print(f"  -> 成功识别并绘制 [{prompt}] (置信度: {score:.2f})")

    if found:
        print(f"  ⏱️ 本次提示词推理耗时: {prompt_duration:.4f} 秒\n")
    else:
        print(f"  -> 未能以高于 {confidence_threshold} 的置信度检测到 [{prompt}]。")
        print(f"  ⏱️ 本次空推理耗时: {prompt_duration:.4f} 秒\n")

    fig.canvas.draw()
    fig.canvas.flush_events()

plt.ioff()
plt.show()