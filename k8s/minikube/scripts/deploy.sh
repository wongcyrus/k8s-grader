#!/bin/bash

# Get the latest Amazon Linux 2023 AMI from SSM Parameter Store
AMIID=$(aws ssm get-parameters --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-x86_64 --region us-east-1 --query 'Parameters[0].Value' --output text)
echo "Using AMI: $AMIID"
INSTANCE_TYPE="t3.medium"
USER_DATA_FILE="userdata.sh"
EBS_SIZE=10
TAG_KEY="Name"
TAG_VALUE="minikube"
SECURITY_GROUP_NAME="minikube-sg"
KEY_PAIR="vockey"

# Create a new security group and get its ID
SECURITY_GROUP_ID=$(aws ec2 create-security-group --group-name $SECURITY_GROUP_NAME --description "Security group for minikube" --query 'GroupId' --output text)

# Allow all traffic from any source
aws ec2 authorize-security-group-ingress --group-id $SECURITY_GROUP_ID --protocol all --port all --cidr 0.0.0.0/0

# Run the instance
aws ec2 run-instances \
    --image-id $AMIID \
    --region us-east-1 \
    --instance-type $INSTANCE_TYPE \
    --user-data file://$USER_DATA_FILE \
    --block-device-mappings DeviceName=/dev/sdh,Ebs={VolumeSize=$EBS_SIZE} \
    --tag-specifications "ResourceType=instance,Tags=[{Key=$TAG_KEY,Value=$TAG_VALUE}]" \
    --security-group-ids $SECURITY_GROUP_ID \
    --key-name $KEY_PAIR