# 您的项目名称
 <img src="https://raw.githubusercontent.com/yangzhaofeng496/TJFusion/main/FusionDocker/assets/logo.png" alt="MARVIN"
  width="520" /># DockerModel

## 前提条件

使用本项目前，需要先完成以下环境准备。

### 1. 安装 Docker

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo systemctl enable docker
sudo systemctl start docker
```

检查是否安装成功：

```bash
docker --version
docker compose version
```

### 2. 安装 Docker GPU 支持

如果需要在容器中使用 GPU，需要安装 NVIDIA Container Toolkit。

```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID) && \
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg && \
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

检查 GPU 是否可用：

```bash
docker run --rm --gpus all nvidia/cuda:12.3.1-base-ubuntu22.04 nvidia-smi
```

### 3. 给 Docker 配置代理

如果拉取镜像或构建时需要代理，可以配置 Docker 的 systemd 代理。

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/http-proxy.conf > /dev/null <<EOF2
[Service]
Environment="HTTP_PROXY=http://127.0.0.1:7890"
Environment="HTTPS_PROXY=http://127.0.0.1:7890"
Environment="NO_PROXY=localhost,127.0.0.1"
EOF2

sudo systemctl daemon-reload
sudo systemctl restart docker
```

检查代理是否生效：

```bash
systemctl show --property=Environment docker
```

## 构建和运行 Docker

### 1. 逐个构建和运行

如果某个 Docker 目录中有 `build.sh`，执行：

```bash
cd /path/to/DockerModel/<docker_dir>
chmod +x build.sh
./build.sh
```

如果某个 Docker 目录中有 `run.sh`，执行：

```bash
cd /path/to/DockerModel/<docker_dir>
chmod +x run.sh
./run.sh
```

### 2. 通过配置文件统一构建和运行

项目支持通过配置文件统一指定要构建和运行的 Docker。
配置TJDocker路径:
```bash
export DOCKER_MODEL_ROOT=Path To TJDocker
```

配置文件路径：

```bash
FusionDocker/configs/docker_launch.yaml
```

先修改这个配置文件，选择需要启用的 Docker。然后使用项目提供的统一启动方式，系统会自动帮助构建所有要运行的 Docker。

### 3. 模型文件说明

  Docker 目录下会有一个 `model` 文件夹，里面包含 `download.sh` 脚本。

  你可以选择以下任一方式准备模型文件：

  1. 进入 `model` 目录后运行 `download.sh` 下载模型。
  2. 也可以将已经准备好的模型文件手动复制到 `model` 目录。

  完成后，请在 `config.yaml` 中将对应的模型路径修改为你实际使用的模型文件路径。

推荐流程：

1. 安装 Docker
2. 如果需要 GPU，再安装 Docker GPU 支持
3. 给 Docker 配置代理
4. 修改 `FusionDocker/configs/docker_launch.yaml`
5. 修改 `下载模型并修改Docker各自的config.yaml`
6. 运行FusionDocker下面的run.sh
