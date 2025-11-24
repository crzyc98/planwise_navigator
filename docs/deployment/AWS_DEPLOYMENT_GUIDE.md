# Fidelity PlanAlign Engine AWS Deployment Guide

**Version:** 1.0
**Last Updated:** 2025-10-31
**Status:** Production Ready

---

## Executive Summary

This guide evaluates AWS deployment options for Fidelity PlanAlign Engine, a workforce simulation platform with event sourcing architecture, DuckDB analytics engine, and Streamlit dashboard.

### Key Findings

| Recommendation | Status | Rationale |
|---------------|--------|-----------|
| **AWS SageMaker** | ❌ **NOT RECOMMENDED** | Architectural mismatch - designed for ML training, not production data pipelines |
| **EC2 + EBS** | ✅ **STRONGLY RECOMMENDED** | Zero code changes, optimal performance, full feature support |
| **ECS/Fargate + EFS** | ⚠️ **VIABLE ALTERNATIVE** | Use if containerization is mandated by organization |
| **AWS Batch** | ⚠️ **FOR SCHEDULED RUNS** | Good for infrequent, scheduled workloads only |

### Quick Decision Tree

```
Do you need containerization?
├─ No  → Use EC2 + EBS (Recommended)
└─ Yes → Do you run 24/7?
         ├─ Yes → Use ECS/Fargate + EFS
         └─ No  → Use AWS Batch + EFS
```

---

## Table of Contents

1. [Application Architecture Overview](#application-architecture-overview)
2. [Why SageMaker Doesn't Fit](#why-sagemaker-doesnt-fit)
3. [Recommended Solution: EC2 + EBS](#recommended-solution-ec2--ebs)
4. [Alternative: ECS/Fargate + EFS](#alternative-ecsfargate--efs)
5. [Cost Comparison](#cost-comparison)
6. [Migration Timeline](#migration-timeline)
7. [Operations & Monitoring](#operations--monitoring)
8. [Appendix: Technical Details](#appendix-technical-details)

---

## Application Architecture Overview

### Technology Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Storage** | DuckDB | 1.0.0 | File-based OLAP database |
| **Transformation** | dbt-core | 1.8.8 | SQL transformation pipeline |
| **Orchestration** | planalign_orchestrator | Custom | Multi-year pipeline execution |
| **CLI** | planalign_cli (Rich + Typer) | 1.0.0 | Command-line interface |
| **Dashboard** | Streamlit | 1.39.0 | Interactive analytics UI |
| **Performance** | Polars | ≥0.20.0 | High-speed data processing |
| **Python** | CPython | 3.11.x | Runtime environment |

### Critical Application Characteristics

1. **File-Based Database**
   - DuckDB file at `dbt/simulation.duckdb` (67MB+, grows with data)
   - Optimized for local SSD storage
   - Requires persistent filesystem

2. **Checkpoint System**
   - `.planalign_checkpoints/` directory for failure recovery
   - Multi-year simulation resume capability
   - Requires persistent state across runs

3. **Long-Running Processes**
   - 2-10 minutes per simulation year
   - Multi-threaded execution (1-16 threads)
   - Batch scenario processing (multiple sequential runs)

4. **Multiple Interfaces**
   - **CLI**: `planalign simulate 2025-2027`
   - **Dashboard**: Streamlit web UI on port 8501
   - **Batch Processing**: `planalign batch --scenarios baseline high_growth`

5. **File I/O Patterns**
   ```
   planalign_engine/
   ├── dbt/simulation.duckdb        # PERSISTENT (67MB+)
   ├── .planalign_checkpoints/      # PERSISTENT (recovery state)
   ├── data/parquet/events/         # PERSISTENT (Parquet outputs)
   ├── logs/                        # PERSISTENT (execution logs)
   └── outputs/                     # PERSISTENT (reports, Excel)
   ```

---

## Why SageMaker Doesn't Fit

### Critical Incompatibilities

#### 1. Ephemeral Storage vs. Persistent Database

**Application Requirement:**
```python
# From planalign_orchestrator/config.py
def get_database_path() -> Path:
    """Get standardized database path..."""
    db_path = os.getenv('DATABASE_PATH', 'dbt/simulation.duckdb')
    return Path(db_path).resolve()
```

**SageMaker Reality:**
- Processing Jobs have ephemeral local storage (deleted after job completion)
- Would require storing DuckDB on EFS (network storage) or S3 sync pattern
- **Problem**: DuckDB is optimized for local SSD - network storage defeats performance benefits

**Workaround Complexity:**
```python
# Required modifications for SageMaker
def get_database_path() -> Path:
    if os.getenv('SM_CHANNEL_DATABASE'):
        # Download from S3 before every run
        s3_download('s3://bucket/simulation.duckdb', '/tmp/simulation.duckdb')

        # Run simulation...

        # Upload to S3 after run (RISK: upload failure = data loss)
        s3_upload('/tmp/simulation.duckdb', 's3://bucket/simulation.duckdb')
```

#### 2. Checkpoint System Incompatibility

**Application Feature:**
```python
# From planalign_orchestrator/pipeline_orchestrator.py
self.checkpoints_dir = Path('.planalign_checkpoints')
self.checkpoints_dir.mkdir(exist_ok=True)
```

**SageMaker Challenge:**
- Checkpoints written to local storage would be lost after job
- Would need S3 sync wrapper on every checkpoint write
- Recovery workflow becomes multi-step S3 process

#### 3. Streamlit Dashboard

**Application Component:** Interactive dashboard at `streamlit_dashboard/`
- Multi-page Streamlit application
- Real-time compensation tuning
- Connects to DuckDB for queries

**SageMaker Reality:**
- **No native support** for hosting web applications
- Would need separate deployment (Fargate, App Runner, or EC2)
- Dashboard would need to connect to DuckDB somehow (S3? Shared EFS?)

#### 4. Rich CLI Interface

**Application Feature:** Beautiful terminal UI with progress bars, tables, colors
```bash
planalign simulate 2025-2027
# Shows: Rich progress bars, live updates, formatted tables
```

**SageMaker Limitation:**
- Processing Jobs capture stdout/stderr to CloudWatch Logs
- No interactive terminal - Rich formatting fails
- Loses polished user experience

#### 5. dbt Project Structure

**Application Structure:** 100+ SQL models in organized directory tree
```
dbt/
├── models/
│   ├── staging/           # 17 models
│   ├── intermediate/      # 62 models
│   └── marts/            # 27 models
├── seeds/                # Configuration CSVs
└── macros/               # Reusable SQL functions
```

**SageMaker Challenge:**
- dbt expects stable project directory
- SageMaker pulls code from S3 on every job start
- Would need to bundle dbt project in container image or fetch from S3 repeatedly

### SageMaker Service Comparison

| Service | Use Case | Fit for PlanWise | Why Not? |
|---------|----------|------------------|----------|
| **SageMaker Studio Notebooks** | Interactive ML development | ❌ Poor | Kernel-based, not for production pipelines |
| **SageMaker Notebook Instances** | Persistent notebooks | ❌ Poor | Stops when idle, notebook-focused |
| **SageMaker Processing Jobs** | Batch data processing | ⚠️ Marginal | Best SageMaker option but still ephemeral |
| **SageMaker Training Jobs** | ML model training | ❌ Poor | Designed for ML, not business logic |
| **SageMaker Pipelines** | ML workflow orchestration | ❌ Poor | Already have PipelineOrchestrator |

### Bottom Line on SageMaker

**Don't force-fit Fidelity PlanAlign Engine into SageMaker.** It's designed for ML training workloads, not production data pipelines with persistent state requirements.

---

## Recommended Solution: EC2 + EBS

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    VPC (us-east-1 / us-west-2)                  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │              Private Subnet (10.0.1.0/24)                 │ │
│  │                                                           │ │
│  │  ┌─────────────────────────────────────────────────┐    │ │
│  │  │   EC2: c6i.2xlarge (Fidelity PlanAlign Engine)        │    │ │
│  │  │   ┌─────────────────────────────────────┐      │    │ │
│  │  │   │ EBS Volume: 100GB gp3 SSD           │      │    │ │
│  │  │   │ /home/ubuntu/planalign_engine/    │      │    │ │
│  │  │   │  ├── dbt/simulation.duckdb          │      │    │ │
│  │  │   │  ├── .planalign_checkpoints/        │      │    │ │
│  │  │   │  ├── data/parquet/events/           │      │    │ │
│  │  │   │  ├── logs/                          │      │    │ │
│  │  │   │  └── outputs/                       │      │    │ │
│  │  │   └─────────────────────────────────────┘      │    │ │
│  │  │                                                 │    │ │
│  │  │   Running Services:                            │    │ │
│  │  │   • planwise CLI (cron/EventBridge)           │    │ │
│  │  │   • Streamlit dashboard (systemd:8501)        │    │ │
│  │  │   • CloudWatch agent (monitoring)              │    │ │
│  │  └─────────────────────────────────────────────────┘    │ │
│  │                            │                             │ │
│  └────────────────────────────┼─────────────────────────────┘ │
│                               │                               │
│  ┌────────────────────────────▼──────────────────────────┐   │
│  │   Application Load Balancer (Public Subnets)         │   │
│  │   • HTTPS:443 → Target Group (EC2:8501)              │   │
│  │   • SSL/TLS Certificate (ACM)                        │   │
│  │   • Security Group: HTTPS from internet              │   │
│  └───────────────────────────────────────────────────────┘   │
│                               │                               │
└───────────────────────────────┼───────────────────────────────┘
                                │
                                ▼
                         Internet Gateway
                                │
                                ▼
                    Users access dashboard via
                    https://planwise.company.com
```

### Why EC2 + EBS is Optimal

| Benefit | Impact |
|---------|--------|
| ✅ **Zero Code Changes** | Application works exactly as designed - no modifications needed |
| ✅ **Optimal DuckDB Performance** | Local SSD storage (not network storage) - fast I/O |
| ✅ **Full Feature Support** | CLI, Streamlit, batch processing all work natively |
| ✅ **Simple Operations** | Standard Linux server management - SSH for debugging |
| ✅ **Persistent State** | EBS volume survives instance stops/starts |
| ✅ **Easy Debugging** | SSH in and run `planwise` commands directly |
| ✅ **Cost Effective** | ~$253/month for production-grade setup |

### Instance Sizing Recommendation

**Recommended Instance:** `c6i.2xlarge` (Compute-Optimized)

| Specification | Value | Rationale |
|--------------|-------|-----------|
| **vCPUs** | 8 | Matches threading config (`dbt_threads: 1-16`, `polars.max_threads: 16`) |
| **Memory** | 16 GB | Handles 4GB adaptive memory manager with headroom |
| **Storage** | 100GB EBS gp3 | Fast SSD for DuckDB, room for growth |
| **Network** | Up to 12.5 Gbps | More than sufficient for dashboard traffic |
| **Cost** | ~$0.34/hour | ~$245/month (24/7 operation) |

**Alternative Instances:**
- **c6i.xlarge** (4 vCPU, 8GB): $122/month - for development/testing
- **c6i.4xlarge** (16 vCPU, 32GB): $490/month - for large-scale production (100K+ employees)

### Deployment Guide

#### Step 1: Launch EC2 Instance

**Via AWS Console:**
1. Navigate to EC2 → Launch Instance
2. **Name:** `planwise-navigator-prod`
3. **AMI:** Amazon Linux 2023 or Ubuntu 22.04 LTS
4. **Instance Type:** c6i.2xlarge
5. **Key Pair:** Create or select existing SSH key
6. **Network:**
   - VPC: Your production VPC
   - Subnet: Private subnet (with NAT Gateway for outbound)
   - Auto-assign Public IP: Disable (use ALB for inbound)
7. **Storage:** 100GB gp3 SSD (3000 IOPS, 125 MB/s throughput)
8. **Security Group:**
   - SSH (22) from your corporate network/VPN
   - Custom TCP (8501) from ALB security group only

**Via AWS CLI:**
```bash
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type c6i.2xlarge \
  --key-name your-key-pair \
  --subnet-id subnet-xxxxx \
  --security-group-ids sg-xxxxx \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":100,"VolumeType":"gp3"}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=planwise-navigator-prod}]'
```

#### Step 2: Initial Setup Script

**SSH into instance:**
```bash
ssh -i your-key.pem ec2-user@<instance-private-ip>
```

**Run setup script:**
```bash
#!/bin/bash
# setup_planalign_engine.sh

set -e  # Exit on error

echo "=== Fidelity PlanAlign Engine Setup ==="

# Update system
sudo yum update -y  # For Amazon Linux
# OR: sudo apt update && sudo apt upgrade -y  # For Ubuntu

# Install Python 3.11
sudo yum install -y python3.11 python3.11-pip git  # Amazon Linux
# OR: sudo apt install -y python3.11 python3.11-venv git  # Ubuntu

# Install uv (fast package installer)
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

# Clone repository
cd /home/ec2-user  # Or /home/ubuntu for Ubuntu
git clone https://github.com/crzyc98/planalign_engine.git
cd planalign_engine

# Setup virtual environment
uv venv .venv --python python3.11
source .venv/bin/activate

# Install dependencies (10-100× faster than pip!)
uv pip install -e ".[dev]"

# Verify installation
planalign health

echo "=== Setup Complete ==="
echo "Next steps:"
echo "1. Configure Streamlit systemd service"
echo "2. Set up scheduled simulations"
echo "3. Configure CloudWatch monitoring"
```

#### Step 3: Configure Streamlit Dashboard Service

**Create systemd service:**
```bash
sudo tee /etc/systemd/system/streamlit-dashboard.service << 'EOF'
[Unit]
Description=Fidelity PlanAlign Engine Streamlit Dashboard
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user/planalign_engine
Environment="PATH=/home/ec2-user/planalign_engine/.venv/bin"
ExecStart=/home/ec2-user/planalign_engine/.venv/bin/streamlit run streamlit_dashboard/main.py --server.port=8501 --server.address=0.0.0.0
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable streamlit-dashboard
sudo systemctl start streamlit-dashboard

# Check status
sudo systemctl status streamlit-dashboard
```

#### Step 4: Configure Application Load Balancer

**Create Target Group:**
```bash
aws elbv2 create-target-group \
  --name planwise-streamlit-tg \
  --protocol HTTP \
  --port 8501 \
  --vpc-id vpc-xxxxx \
  --health-check-path / \
  --health-check-interval-seconds 30 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3

# Register EC2 instance as target
aws elbv2 register-targets \
  --target-group-arn arn:aws:elasticloadbalancing:... \
  --targets Id=i-xxxxx  # Your EC2 instance ID
```

**Create Application Load Balancer:**
```bash
# Create ALB
aws elbv2 create-load-balancer \
  --name planwise-alb \
  --subnets subnet-public1 subnet-public2 \
  --security-groups sg-alb \
  --scheme internet-facing

# Create HTTPS listener (requires ACM certificate)
aws elbv2 create-listener \
  --load-balancer-arn arn:aws:elasticloadbalancing:... \
  --protocol HTTPS \
  --port 443 \
  --certificates CertificateArn=arn:aws:acm:... \
  --default-actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:...
```

**Security Group Rules:**
```bash
# ALB Security Group (sg-alb)
# Inbound: HTTPS (443) from 0.0.0.0/0
# Outbound: TCP (8501) to EC2 security group

# EC2 Security Group (sg-ec2)
# Inbound: TCP (8501) from ALB security group
# Inbound: SSH (22) from corporate network
# Outbound: All traffic (for package downloads, etc.)
```

#### Step 5: Schedule Simulations

**Option A: Cron (Simple)**
```bash
# Edit crontab
crontab -e

# Add scheduled simulation (runs nightly at 2 AM)
0 2 * * * cd /home/ec2-user/planalign_engine && source .venv/bin/activate && planalign batch --scenarios baseline >> /var/log/planwise-batch.log 2>&1

# Add weekly comprehensive run (Sundays at midnight)
0 0 * * 0 cd /home/ec2-user/planalign_engine && source .venv/bin/activate && planalign simulate 2025-2030 --export-format excel >> /var/log/planwise-weekly.log 2>&1
```

**Option B: EventBridge + Systems Manager (Production)**
```yaml
# EventBridge Rule
Name: planwise-nightly-batch
Schedule: cron(0 2 * * ? *)
Target: AWS Systems Manager Run Command
Document: AWS-RunShellScript
Parameters:
  commands:
    - cd /home/ec2-user/planalign_engine
    - source .venv/bin/activate
    - planalign batch --scenarios baseline high_growth
  instanceIds:
    - i-xxxxx  # Your EC2 instance ID
```

#### Step 6: Configure CloudWatch Monitoring

**Install CloudWatch Agent:**
```bash
# Download and install
wget https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm
sudo rpm -U ./amazon-cloudwatch-agent.rpm

# Configure agent
sudo tee /opt/aws/amazon-cloudwatch-agent/etc/config.json << 'EOF'
{
  "metrics": {
    "namespace": "PlanWiseNavigator",
    "metrics_collected": {
      "cpu": {"measurement": [{"name": "cpu_usage_idle"}], "totalcpu": false},
      "disk": {
        "measurement": [{"name": "used_percent"}],
        "resources": ["/"]
      },
      "mem": {"measurement": [{"name": "mem_used_percent"}]}
    }
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/home/ec2-user/planalign_engine/logs/*.log",
            "log_group_name": "/planwise/application",
            "log_stream_name": "{instance_id}"
          },
          {
            "file_path": "/var/log/planwise-*.log",
            "log_group_name": "/planwise/scheduled-jobs",
            "log_stream_name": "{instance_id}"
          }
        ]
      }
    }
  }
}
EOF

# Start agent
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -s \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/config.json
```

**Create CloudWatch Alarms:**
```bash
# High CPU alarm
aws cloudwatch put-metric-alarm \
  --alarm-name planwise-high-cpu \
  --alarm-description "Alert when CPU exceeds 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/EC2 \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=InstanceId,Value=i-xxxxx \
  --evaluation-periods 2 \
  --alarm-actions arn:aws:sns:us-east-1:123456789:planwise-alerts

# Disk space alarm
aws cloudwatch put-metric-alarm \
  --alarm-name planwise-low-disk \
  --alarm-description "Alert when disk usage exceeds 80%" \
  --metric-name disk_used_percent \
  --namespace PlanWiseNavigator \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:us-east-1:123456789:planwise-alerts
```

#### Step 7: Configure Backups

**EBS Snapshot Backup via AWS Backup:**
```bash
# Create backup vault
aws backup create-backup-vault --backup-vault-name planwise-backups

# Create backup plan
aws backup create-backup-plan --cli-input-json '{
  "BackupPlan": {
    "BackupPlanName": "planwise-daily-backups",
    "Rules": [
      {
        "RuleName": "DailyBackups",
        "TargetBackupVaultName": "planwise-backups",
        "ScheduleExpression": "cron(0 5 * * ? *)",
        "StartWindowMinutes": 60,
        "CompletionWindowMinutes": 120,
        "Lifecycle": {
          "DeleteAfterDays": 30
        }
      }
    ]
  }
}'

# Assign resources (EC2 instance)
aws backup create-backup-selection --cli-input-json '{
  "BackupPlanId": "backup-plan-id",
  "BackupSelection": {
    "SelectionName": "planwise-ec2",
    "IamRoleArn": "arn:aws:iam::123456789:role/AWSBackupRole",
    "Resources": ["arn:aws:ec2:us-east-1:123456789:instance/i-xxxxx"]
  }
}'
```

### Operational Workflows

#### Running Simulations

**Interactive Execution (Development):**
```bash
# SSH into instance
ssh -i your-key.pem ec2-user@<instance-ip>

# Activate environment
cd planalign_engine
source .venv/bin/activate

# Run single simulation
planalign simulate 2025-2027 --verbose

# Run batch scenarios
planalign batch --scenarios baseline high_growth --export-format excel

# Check status
planalign status --detailed
```

**Scheduled Execution (Production):**
- Configured via cron or EventBridge
- Logs written to `/var/log/planwise-*.log`
- Outputs saved to `outputs/` directory
- CloudWatch Logs for centralized monitoring

#### Accessing Dashboard

**Users navigate to:** `https://planwise.company.com`
- ALB terminates SSL/TLS
- Routes to EC2 instance port 8501
- Streamlit dashboard loads in browser
- Real-time queries against DuckDB

#### Debugging Failed Runs

```bash
# SSH into instance
ssh -i your-key.pem ec2-user@<instance-ip>

# Check application logs
cd planalign_engine
tail -f logs/*.log

# Check scheduled job logs
tail -f /var/log/planwise-*.log

# Check Streamlit service
sudo systemctl status streamlit-dashboard
sudo journalctl -u streamlit-dashboard -f

# Query DuckDB directly
duckdb dbt/simulation.duckdb "SELECT COUNT(*) FROM fct_yearly_events"

# Check checkpoints for recovery
planalign checkpoints list
planalign checkpoints status
```

### Cost Breakdown

| Component | Specification | Monthly Cost (us-east-1) |
|-----------|--------------|-------------------------|
| **EC2 Instance** | c6i.2xlarge (8 vCPU, 16GB) | ~$245 |
| **EBS Storage** | 100GB gp3 SSD | ~$8 |
| **Application Load Balancer** | Standard ALB | ~$23 |
| **Data Transfer** | Out to internet (assume 50GB) | ~$5 |
| **CloudWatch Logs** | 5GB ingestion, 1GB storage | ~$3 |
| **AWS Backup** | Daily snapshots, 30-day retention | ~$5 |
| **Total** | | **~$289/month** |

**Cost Optimization Options:**
- Use Savings Plan (1-year): Save 27% (~$210/month)
- Use Reserved Instance (1-year): Save 30% (~$202/month)
- Stop instance during off-hours: Save 50% (~$145/month for 12-hour days)

---

## Alternative: ECS/Fargate + EFS

### When to Consider This Option

✅ **Use ECS/Fargate if:**
- Organization mandates containerized deployments
- Want managed infrastructure (no EC2 patching)
- Need auto-scaling for variable workloads
- Have existing ECS operational expertise

⚠️ **Trade-offs:**
- More complex setup (Docker, task definitions, ECS orchestration)
- EFS latency vs. local SSD (though may not impact significantly)
- Need to modify code for S3 output syncing

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        AWS Infrastructure                        │
│                                                                 │
│  ┌───────────────────────────────────────────────────────┐    │
│  │   EFS: Persistent Storage                             │    │
│  │   /mnt/data/                                          │    │
│  │   ├── simulation.duckdb                               │    │
│  │   ├── .planalign_checkpoints/                         │    │
│  │   └── outputs/                                        │    │
│  └────────────────┬──────────────────────────────────────┘    │
│                   │                                            │
│                   │ (mounted by both containers)               │
│                   │                                            │
│  ┌────────────────▼────────────────┐  ┌──────────────────────┐ │
│  │  ECS Fargate Task               │  │  ECS Fargate Service │ │
│  │  (Scheduled via EventBridge)    │  │  (24/7 running)      │ │
│  │                                 │  │                      │ │
│  │  planwise-batch-processor      │  │  streamlit-dashboard │ │
│  │  • CPU: 4096 (4 vCPU)          │  │  • CPU: 2048         │ │
│  │  • Memory: 8192 MB             │  │  • Memory: 4096 MB   │ │
│  │  • Triggered by EventBridge     │  │  • Port 8501         │ │
│  │  • Runs batch scenarios         │  │  • Auto-scaling: 1-3 │ │
│  └─────────────────────────────────┘  └──────────┬───────────┘ │
│                                                   │             │
│  ┌────────────────────────────────────────────────▼─────────┐  │
│  │    Application Load Balancer (HTTPS:443)                │  │
│  │    • SSL/TLS termination                                │  │
│  │    • Routes to ECS Service                              │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Implementation Guide

#### Step 1: Create Dockerfile

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy application files
COPY . /app

# Install uv for fast package installation
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Install dependencies
RUN uv venv .venv && \
    . .venv/bin/activate && \
    uv pip install -e "."

# Expose Streamlit port
EXPOSE 8501

# Default command (overridden by task definition)
CMD ["/app/.venv/bin/planwise", "health"]
```

#### Step 2: Build and Push to ECR

```bash
# Create ECR repository
aws ecr create-repository --repository-name planwise-navigator

# Get login credentials
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com

# Build image
docker build -t planwise-navigator:latest .

# Tag and push
docker tag planwise-navigator:latest 123456789.dkr.ecr.us-east-1.amazonaws.com/planwise-navigator:latest
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/planwise-navigator:latest
```

#### Step 3: Create EFS Filesystem

```bash
# Create EFS
aws efs create-file-system \
  --creation-token planwise-efs \
  --performance-mode generalPurpose \
  --throughput-mode bursting \
  --tags Key=Name,Value=planwise-navigator-efs

# Create mount targets in each AZ
aws efs create-mount-target \
  --file-system-id fs-xxxxx \
  --subnet-id subnet-private1 \
  --security-groups sg-efs

aws efs create-mount-target \
  --file-system-id fs-xxxxx \
  --subnet-id subnet-private2 \
  --security-groups sg-efs
```

#### Step 4: Create ECS Task Definitions

**Batch Processing Task:**
```json
{
  "family": "planwise-batch-processor",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "4096",
  "memory": "8192",
  "executionRoleArn": "arn:aws:iam::123456789:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::123456789:role/planwiseTaskRole",
  "containerDefinitions": [
    {
      "name": "planwise-batch",
      "image": "123456789.dkr.ecr.us-east-1.amazonaws.com/planwise-navigator:latest",
      "command": [
        "/app/.venv/bin/planwise",
        "batch",
        "--scenarios",
        "baseline",
        "high_growth"
      ],
      "mountPoints": [
        {
          "sourceVolume": "efs-storage",
          "containerPath": "/mnt/data"
        }
      ],
      "environment": [
        {"name": "DATABASE_PATH", "value": "/mnt/data/simulation.duckdb"},
        {"name": "CHECKPOINTS_DIR", "value": "/mnt/data/.planalign_checkpoints"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/planwise-batch",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "batch"
        }
      }
    }
  ],
  "volumes": [
    {
      "name": "efs-storage",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-xxxxx",
        "transitEncryption": "ENABLED"
      }
    }
  ]
}
```

**Streamlit Dashboard Service:**
```json
{
  "family": "planwise-streamlit-dashboard",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "2048",
  "memory": "4096",
  "executionRoleArn": "arn:aws:iam::123456789:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::123456789:role/planwiseTaskRole",
  "containerDefinitions": [
    {
      "name": "streamlit-dashboard",
      "image": "123456789.dkr.ecr.us-east-1.amazonaws.com/planwise-navigator:latest",
      "command": [
        "/app/.venv/bin/streamlit",
        "run",
        "streamlit_dashboard/main.py",
        "--server.port=8501",
        "--server.address=0.0.0.0"
      ],
      "portMappings": [
        {
          "containerPort": 8501,
          "protocol": "tcp"
        }
      ],
      "mountPoints": [
        {
          "sourceVolume": "efs-storage",
          "containerPath": "/mnt/data"
        }
      ],
      "environment": [
        {"name": "DATABASE_PATH", "value": "/mnt/data/simulation.duckdb"}
      ],
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8501/_stcore/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      },
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/planwise-streamlit",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "dashboard"
        }
      }
    }
  ],
  "volumes": [
    {
      "name": "efs-storage",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-xxxxx",
        "transitEncryption": "ENABLED"
      }
    }
  ]
}
```

#### Step 5: Create ECS Services

**Streamlit Dashboard Service (24/7):**
```bash
aws ecs create-service \
  --cluster planwise-cluster \
  --service-name streamlit-dashboard \
  --task-definition planwise-streamlit-dashboard:1 \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-private1,subnet-private2],securityGroups=[sg-ecs],assignPublicIp=DISABLED}" \
  --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:...,containerName=streamlit-dashboard,containerPort=8501
```

#### Step 6: Schedule Batch Tasks

**EventBridge Rule for Nightly Runs:**
```json
{
  "RuleName": "planwise-nightly-batch",
  "ScheduleExpression": "cron(0 2 * * ? *)",
  "State": "ENABLED",
  "Targets": [
    {
      "Arn": "arn:aws:ecs:us-east-1:123456789:cluster/planwise-cluster",
      "RoleArn": "arn:aws:iam::123456789:role/ecsEventsRole",
      "EcsParameters": {
        "TaskDefinitionArn": "arn:aws:ecs:us-east-1:123456789:task-definition/planwise-batch-processor:1",
        "TaskCount": 1,
        "LaunchType": "FARGATE",
        "NetworkConfiguration": {
          "awsvpcConfiguration": {
            "Subnets": ["subnet-private1", "subnet-private2"],
            "SecurityGroups": ["sg-ecs"],
            "AssignPublicIp": "DISABLED"
          }
        }
      }
    }
  ]
}
```

### Cost Breakdown (ECS/Fargate)

| Component | Specification | Monthly Cost (us-east-1) |
|-----------|--------------|-------------------------|
| **Fargate (Streamlit)** | 2 vCPU, 4GB, 24/7 | ~$73 |
| **Fargate (Batch Tasks)** | 4 vCPU, 8GB, 1 hour/day | ~$18 |
| **EFS** | 100GB storage, moderate throughput | ~$30 |
| **Application Load Balancer** | Standard ALB | ~$23 |
| **Data Transfer** | Out to internet (assume 50GB) | ~$5 |
| **CloudWatch Logs** | 5GB ingestion, 1GB storage | ~$3 |
| **Total** | | **~$152/month** |

**Note:** This assumes only 1 hour/day of batch processing. If running 24/7, Fargate cost would be ~$365/month, making total ~$499/month (more expensive than EC2).

---

## Cost Comparison

### Detailed Cost Analysis (us-east-1, 24/7 operation)

| Solution | Compute | Storage | Networking | Monitoring | Total/Month | Best For |
|----------|---------|---------|-----------|-----------|-------------|----------|
| **EC2 + EBS** | $245 | $8 | $28 | $8 | **$289** | Production, full features |
| **ECS/Fargate + EFS** (24/7 batch) | $365 | $30 | $28 | $3 | **$426** | Containerization mandate |
| **ECS/Fargate + EFS** (1hr/day batch) | $91 | $30 | $28 | $3 | **$152** | Infrequent batch runs |
| **AWS Batch + EFS** (1hr/day) | $62 | $30 | $28 | $3 | **$123** | Scheduled workloads only |

### Cost Optimization Strategies

#### EC2 Cost Reduction

**Option 1: Savings Plans (1-year commitment)**
- Save 27% on compute: $245 → $179/month
- **Total: ~$220/month** (save $69/month)

**Option 2: Reserved Instances (1-year, no upfront)**
- Save 30% on compute: $245 → $172/month
- **Total: ~$213/month** (save $76/month)

**Option 3: Reserved Instances (1-year, all upfront)**
- Save 40% on compute: $245 → $147/month
- **Total: ~$188/month** (save $101/month)

**Option 4: Auto-scaling with off-hours shutdown**
- Run 12 hours/day (business hours): $245 → $123/month
- **Total: ~$164/month** (save $125/month)
- **Trade-off:** Dashboard unavailable during off-hours

#### ECS/Fargate Cost Reduction

**Option 1: Fargate Spot (70% discount for interruptible batch jobs)**
- Batch processing: $18 → $5/month
- **Total: ~$139/month** for 1hr/day batch

**Option 2: Scheduled scaling for dashboard**
- Run dashboard 12 hours/day: $73 → $37/month
- **Total: ~$116/month**
- **Trade-off:** Dashboard unavailable during off-hours

### Total Cost of Ownership (3 Years)

| Solution | Monthly | 3-Year Total | 3-Year w/ Reserved (EC2) / Savings (Fargate) |
|----------|---------|--------------|----------------------------------------------|
| **EC2 + EBS** | $289 | $10,404 | **$7,668** (27% savings) |
| **ECS/Fargate (1hr/day)** | $152 | $5,472 | **$5,040** (with Fargate Spot) |
| **ECS/Fargate (24/7)** | $426 | $15,336 | **$13,320** (with Compute Savings Plans) |

---

## Migration Timeline

### Phase 1: POC Deployment (1-2 weeks)

**Objectives:**
- Validate Fidelity PlanAlign Engine functionality on AWS
- Test simulation performance on EC2
- Verify dashboard accessibility

**Tasks:**
- [ ] Launch EC2 c6i.xlarge in development VPC
- [ ] Manual deployment via SSH
- [ ] Run test simulation (2025-2027)
- [ ] Configure basic Streamlit access
- [ ] Test batch scenario processing
- [ ] Validate DuckDB performance on EBS gp3

**Success Criteria:**
- Simulation completes successfully
- Performance matches on-premise baseline
- Dashboard loads and queries DuckDB

### Phase 2: Production Hardening (2-3 weeks)

**Objectives:**
- Production-grade infrastructure
- High availability and monitoring
- Automated backup and recovery

**Tasks:**
- [ ] Upgrade to c6i.2xlarge in production VPC
- [ ] Configure Application Load Balancer with SSL/TLS
- [ ] Set up AWS Backup for daily EBS snapshots
- [ ] Implement CloudWatch monitoring and alarms
- [ ] Configure EventBridge for scheduled simulations
- [ ] Set up IAM roles with least-privilege access
- [ ] Implement security group hardening
- [ ] Configure VPC Flow Logs for network monitoring

**Success Criteria:**
- Dashboard accessible via HTTPS
- Scheduled simulations run automatically
- CloudWatch alarms configured and tested
- Backups verified with recovery test

### Phase 3: Operational Excellence (2-3 weeks)

**Objectives:**
- Streamlined operations and maintenance
- Documentation and runbooks
- Team training

**Tasks:**
- [ ] Document operational procedures
- [ ] Create runbooks for common issues
- [ ] Implement Systems Manager Session Manager (SSH alternative)
- [ ] Set up AWS Systems Manager Patch Manager
- [ ] Configure log aggregation and retention
- [ ] Implement cost tracking with AWS Cost Explorer tags
- [ ] Conduct team training on AWS operations
- [ ] Perform disaster recovery drill

**Success Criteria:**
- Team can operate independently
- All procedures documented
- DR plan validated

### Total Timeline: 5-8 weeks

**Parallel Workstreams:**
- Infrastructure setup (Weeks 1-3)
- Application deployment (Weeks 2-4)
- Monitoring and operations (Weeks 3-6)
- Documentation and training (Weeks 5-8)

---

## Operations & Monitoring

### Health Checks

**Application-Level Health:**
```bash
# Run on EC2 instance
planalign health

# Expected output:
# ✓ Python 3.11 installed
# ✓ DuckDB connection successful
# ✓ dbt project found
# ✓ Configuration valid
# ✓ Dependencies satisfied
```

**System-Level Health:**
```bash
# CPU and memory
top

# Disk space
df -h /home/ec2-user/planalign_engine

# Database size
du -sh dbt/simulation.duckdb

# Streamlit service status
sudo systemctl status streamlit-dashboard
```

### CloudWatch Dashboards

**Recommended Dashboard Widgets:**

1. **Compute Metrics:**
   - EC2 CPU Utilization (Average, Max)
   - EC2 Memory Utilization (Average, Max)
   - EC2 Network In/Out

2. **Storage Metrics:**
   - EBS Volume Read/Write Bytes
   - EBS Volume Read/Write Ops
   - Disk Used Percent (custom metric)

3. **Application Metrics:**
   - Simulation Success Rate (custom metric)
   - Simulation Duration (custom metric)
   - Active Dashboard Users (Streamlit logs)

4. **ALB Metrics:**
   - Target Response Time
   - Healthy Host Count
   - HTTP 5xx Error Rate

### Log Management

**Log Locations:**
- Application logs: `/home/ec2-user/planalign_engine/logs/*.log`
- Scheduled job logs: `/var/log/planwise-*.log`
- Streamlit logs: `sudo journalctl -u streamlit-dashboard`
- System logs: `/var/log/messages` or `/var/log/syslog`

**CloudWatch Logs Configuration:**
```json
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/home/ec2-user/planalign_engine/logs/*.log",
            "log_group_name": "/planwise/application",
            "log_stream_name": "{instance_id}"
          }
        ]
      }
    }
  }
}
```

**Log Retention:**
- Application logs: 30 days
- Audit logs: 1 year
- Debug logs: 7 days

### Alerting Strategy

**Critical Alerts (PagerDuty / SNS):**
- EC2 instance down (StatusCheckFailed)
- Disk space > 90%
- Simulation failure (custom metric)
- Dashboard unavailable (ALB unhealthy target)

**Warning Alerts (Email / Slack):**
- CPU > 80% for 10 minutes
- Memory > 85% for 5 minutes
- Disk space > 75%
- Long-running simulation (> 15 minutes)

**Informational Alerts (Email):**
- Daily simulation completion summary
- Weekly backup success confirmation
- Monthly cost report

### Disaster Recovery

**RPO (Recovery Point Objective): 24 hours**
- Daily EBS snapshots via AWS Backup
- Most recent data loss: up to 24 hours

**RTO (Recovery Time Objective): 2 hours**
1. Restore EBS volume from snapshot (30 minutes)
2. Launch new EC2 instance with restored volume (10 minutes)
3. Update ALB target group (5 minutes)
4. Verify application functionality (30 minutes)
5. Update DNS if needed (30 minutes)
6. Buffer for troubleshooting (15 minutes)

**DR Procedure:**
```bash
# 1. Create volume from snapshot
aws ec2 create-volume \
  --snapshot-id snap-xxxxx \
  --availability-zone us-east-1a

# 2. Launch new EC2 instance
aws ec2 run-instances \
  --image-id ami-xxxxx \
  --instance-type c6i.2xlarge \
  --key-name recovery-key

# 3. Attach restored volume
aws ec2 attach-volume \
  --volume-id vol-xxxxx \
  --instance-id i-xxxxx \
  --device /dev/sdf

# 4. Mount volume and verify
sudo mount /dev/sdf /mnt/recovery
ls -la /mnt/recovery/planalign_engine

# 5. Register with ALB
aws elbv2 register-targets \
  --target-group-arn arn:aws:... \
  --targets Id=i-xxxxx
```

### Maintenance Windows

**Recommended Schedule:**
- **OS Patching:** Monthly, Sundays 2-4 AM ET
- **Application Updates:** As needed, Tuesdays 10 PM ET
- **Database Maintenance:** Quarterly, Saturdays 12 AM ET

**Maintenance Procedure:**
```bash
# 1. Create snapshot before maintenance
aws ec2 create-snapshot \
  --volume-id vol-xxxxx \
  --description "Pre-maintenance snapshot"

# 2. Deregister from ALB (disable new traffic)
aws elbv2 deregister-targets \
  --target-group-arn arn:aws:... \
  --targets Id=i-xxxxx

# 3. Perform maintenance
sudo yum update -y
sudo systemctl restart streamlit-dashboard

# 4. Verify functionality
planalign health
curl http://localhost:8501

# 5. Re-register with ALB
aws elbv2 register-targets \
  --target-group-arn arn:aws:... \
  --targets Id=i-xxxxx
```

---

## Appendix: Technical Details

### A. Application Performance Characteristics

**Based on E067/E068 Performance Optimizations:**

| Metric | Value | Notes |
|--------|-------|-------|
| **Simulation Speed** | 2-10 min/year | Depends on workforce size (100-100K employees) |
| **Threading** | 1-16 threads | Configurable via `dbt_threads`, `polars.max_threads` |
| **Memory Usage** | 2-4 GB | Adaptive memory manager (E063) |
| **Database Size** | 67MB baseline | Grows ~10-50MB per simulation year |
| **Parquet Storage** | 60% I/O reduction | E068 storage optimization |
| **Polars Mode** | 375× speedup | 0.16s vs 60s for event generation |

**Storage Growth Projections:**
- 5-year simulation: ~300MB total
- 10-year simulation: ~600MB total
- 100 scenarios: ~30GB total (batch processing)

### B. Security Considerations

**Network Security:**
- Private subnet for EC2 (no direct internet access)
- NAT Gateway for outbound internet (package downloads)
- ALB in public subnet with SSL/TLS termination
- Security groups with least-privilege rules
- VPC Flow Logs for network monitoring

**Access Control:**
- IAM roles for EC2 (no long-term credentials)
- SSH access restricted to corporate network/VPN
- Dashboard access via HTTPS only (no HTTP)
- MFA required for AWS Console access
- Secrets Manager for any API keys/credentials

**Data Protection:**
- EBS volumes encrypted at rest (AWS KMS)
- EFS encrypted at rest and in transit
- EBS snapshots encrypted
- S3 encryption for outputs (if used)
- VPC endpoints for AWS service access (no internet routing)

**Compliance:**
- No PII/PHI stored in simulation data
- Audit logging via CloudTrail
- Config rules for compliance monitoring
- Regular vulnerability scanning (AWS Inspector)

### C. Troubleshooting Guide

**Problem: Simulation Fails with "Database Locked"**

**Cause:** Another process has exclusive lock on DuckDB

**Solution:**
```bash
# Check for active connections
lsof | grep simulation.duckdb

# Kill stale processes
kill -9 <PID>

# Verify no locks remain
duckdb dbt/simulation.duckdb "PRAGMA database_list"
```

**Problem: Dashboard Shows "Connection Error"**

**Cause:** Streamlit service not running or DuckDB unreachable

**Solution:**
```bash
# Check Streamlit service
sudo systemctl status streamlit-dashboard

# Restart if needed
sudo systemctl restart streamlit-dashboard

# Check logs
sudo journalctl -u streamlit-dashboard -n 100

# Test database access
duckdb dbt/simulation.duckdb "SELECT 1"
```

**Problem: High Memory Usage**

**Cause:** Large simulation with insufficient memory configuration

**Solution:**
```bash
# Check current memory usage
free -h

# Adjust adaptive memory manager in config/simulation_config.yaml
optimization:
  memory_limit_gb: 8.0  # Increase from 4.0
  adaptive_memory_management:
    low_threshold_gb: 4.0
    medium_threshold_gb: 6.0
    high_threshold_gb: 8.0

# Or reduce threading
dbt_threads: 2  # Down from 4
```

**Problem: Slow DuckDB Queries**

**Cause:** EFS latency (if using ECS/Fargate)

**Solution:**
- Use EFS Provisioned Throughput mode
- Increase throughput: 100 MB/s → 250 MB/s
- OR: Move to EC2 + EBS for local SSD performance

### D. Future Enhancements

**Potential Improvements:**
1. **Multi-Region Deployment** for disaster recovery
2. **Auto Scaling Group** for high availability
3. **API Gateway + Lambda** for programmatic access
4. **S3 Data Lake** integration for long-term analytics
5. **QuickSight Dashboards** for executive reporting
6. **Step Functions** for complex multi-scenario orchestration

---

## Conclusion

**Executive Recommendation: Deploy on EC2 + EBS**

Fidelity PlanAlign Engine is a production data pipeline with persistent state requirements, not an ML training workload. AWS EC2 with EBS storage provides:

✅ **Zero code changes** - works exactly as designed
✅ **Optimal performance** - local SSD for DuckDB
✅ **Full feature support** - CLI, Streamlit, batch processing
✅ **Simple operations** - standard Linux server management
✅ **Cost effective** - ~$289/month production-ready

**Do not use SageMaker.** It introduces significant architectural complexity without benefits for this use case.

**Consider ECS/Fargate** only if containerization is organizationally mandated, with the understanding that EFS latency is a trade-off vs. local storage performance.

---

## Questions & Support

For questions about this deployment guide, contact:
- **Infrastructure Team:** [Email/Slack Channel]
- **Application Team:** [Email/Slack Channel]
- **AWS Support:** [Support Plan Details]

**Document Maintenance:**
- Review: Quarterly
- Owner: [Name/Team]
- Last Reviewed: 2025-10-31
