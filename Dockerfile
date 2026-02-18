FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/root/.local/bin:$PATH" \
    CDK_DISABLE_TYPEGUARD=1

# Install system dependencies, Node.js and Docker CLI
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    git \
    bash \
    docker.io \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install AWS CLI, boto3 and CDK
RUN pip install --no-cache-dir awscli boto3 \
    && npm install -g aws-cdk@latest

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

# Verify installations
RUN cdk --version && aws --version && docker --version

CMD [ "bash" ]
