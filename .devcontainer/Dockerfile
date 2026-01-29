FROM ubuntu:24.04

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

# Install Python and essential tools
RUN apt-get update && \
    apt-get install -y \
    software-properties-common \
    git \
    curl \
    wget \
    ca-certificates \
    gnupg \
    lsb-release \
    sudo && \
    # Add deadsnakes PPA for Python 3.14
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.14 python3.14-venv python3.14-dev python3-pip && \
    # Create python symlink
    ln -sf /usr/bin/python3.14 /usr/bin/python && \
    ln -sf /usr/bin/python3.14 /usr/bin/python3 && \
    # Install Docker CLI
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    chmod a+r /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && \
    apt-get install -y docker-ce-cli docker-compose-plugin && \
    # Clean up
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Create a non-root user (handle existing ubuntu user with GID 1000)
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN if getent group $USER_GID; then \
        groupmod -n $USERNAME $(getent group $USER_GID | cut -d: -f1); \
    else \
        groupadd --gid $USER_GID $USERNAME; \
    fi && \
    if getent passwd $USER_UID; then \
        usermod -l $USERNAME -d /home/$USERNAME -m $(getent passwd $USER_UID | cut -d: -f1); \
    else \
        useradd --uid $USER_UID --gid $USER_GID -m $USERNAME -s /bin/bash; \
    fi && \
    echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME && \
    chmod 0440 /etc/sudoers.d/$USERNAME

# Add user to docker group for socket access
# The docker group will be added with the host's GID via runArgs
RUN groupadd -f docker || true
RUN usermod -aG docker $USERNAME || true

USER $USERNAME
