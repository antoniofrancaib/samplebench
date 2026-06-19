# Introduction to the cluster

_Posted: October 24, 2025 | Updated: February 17, 2026 | By: Stephan Stadlbauer | Views: 609_

## Key Usage Policies & Information

### Initial Operations Phase

The cluster is currently in its initial operational phase. While we strive for stability, unexpected downtimes may occur. Planned maintenance for services and updates will be announced in advance via email.

### Essential Policies

- **Your Data, Your Responsibility:** The cluster storage is **NOT BACKED UP**. You are solely responsible for backing up your critical data, results, and code. We strongly recommend using version control (Git) with regular commits and maintaining external backups of important results.
    
- **Fair Use of Resources:** This is a shared system. Please use resources efficiently and responsibly. Do not run computationally intensive jobs on the login nodes, as this degrades performance for all users. All computations must be submitted through the Slurm scheduler.
    
- **Resource Abuse:** Deliberately monopolizing resources, attempting to bypass the scheduler, or running jobs that disrupt system stability is strictly prohibited and will result in the suspension of your account.
    
- **Guest User Access:** As a guest user, please note that AITHYRA local users have priority access to cluster resources. During periods of high demand, guest access may be temporarily limited or suspended to ensure service continuity for local users.
    

### Software Environment

- **Module System Status:** The cluster uses Lmod for software environment management. The module system is currently being configured and expanded. Comprehensive documentation for available software modules will be added soon. Check back regularly or contact IT Services for updates.
    
- **Powered by Slurm:** The cluster uses the Slurm Workload Manager to schedule and manage all computational jobs. Mastering Slurm is your gateway to efficient computing.
    

> **Need Help?** > * **Scientific Computing Team:** itservices@aithyra.ac.at
> 
> - **Responsible:** Stephan Stadlbauer (stephan.stadlbauer@aithyra.ac.at)
>     

## Getting Started: First Steps

### Connecting to the Cluster

There are three ways to access the cluster:

1. **Direct SSH (From AITHYRA Network):** If you’re on the internal network, use `ssh your_username@login01.hpc.aithyra.ac.at` or `ssh your_username@login02.hpc.aithyra.ac.at`.
    
2. **SSH via Jump Host (External Access):** From outside the network, use our jump host. See the detailed Jump SSH Guide for configuration.
    
3. **Web Browser (JupyterHub):** Access the cluster via [https://jupyter.aithyra.at](https://jupyter.aithyra.at/). This provides a graphical interface ideal for interactive development, data exploration, and notebook-based workflows.
    

## Storage & File Systems

Understanding where to store your data is crucial for optimal performance. The cluster provides different storage areas optimized for specific use cases.

|**Storage Location**|**Path**|**Best For**|**Performance**|**Backup**|
|---|---|---|---|---|
|**Home Directory**|`/mnt/labs/home/[username]`<br><br>  <br><br>`/mnt/nfs/vol8t/home/[username]`|Source code, scripts, config files, small datasets|Medium (NFS, spinning disks)|Partly, reliable|
|**Group Directory**|`/mnt/labs/data/[group_name]`|Shared datasets and results|Medium (NFS)|Partly, reliable|
|**Shared Data (Local)**|`/mnt/labs/shared`|Datasets shared across AITHYRA|Medium (NFS)|No|
|**Shared Data (Azure)**|`/nfsdata/AITHYRA/shared`|Data for H100 Azure node computations|Medium (Azure NFS)|No, but reliable|
|**Local Scratch**|`/scratch`|Temporary job data, I/O-intensive ops|Very High (Local NVMe SSD)|No|
|**Shared Scratch (Azure)**|`/netscratch`|Temporary job data, shared I/O intensive jobs|High, shared BeeGFS|No|

### Storage Best Practices

- **Home Directory:** Available on all nodes. OK for source code, scripts, and storing final results. Avoid using for I/O-heavy workloads, compiling, training datasets, or frequent read/write operations due to network spinning disks.
    
- **Group Directory:** Shared persistent storage within your research group. All group members have read/write access.
    
- **Shared Data (Local):** Create your own folder (`mkdir /mnt/labs/shared/your_project`). Set permissions carefully to restrict access to your group (`chgrp your_group ... && chmod 770 ...`).
    
- **Shared Data (Azure):** Use this for all H100 Azure node computations. Create a personal folder and secure it immediately (`chmod 700`). Note that home directories are very slow on Azure nodes.
    
- **Local Scratch Storage:** Fastest storage option via local NVMe SSDs (`/scratch`). Create a personal folder for temporary job data and clean it up regularly.
    
- **Network Scratch Storage (Azure Only):** Fast storage option via BeeGFS network filesystem (`/netscratch`). Create a personal folder for temporary job data and clean it up regularly.
    

### Data Transfer Strategy for Azure H100 Nodes

When working with Azure H100 nodes, follow this workflow to avoid performance issues:

1. **Prepare your data:** Organize datasets in your home directory initially.
    
2. **Copy to Azure storage:** Before running computations, transfer data to `/nfsdata/AITHYRA/shared/your_username/`.
    
3. **Use a transfer job in tmux:** For large datasets, run the copy operation as a job to avoid timeouts.
    

Bash

```
# Start a persistent terminal session
tmux new -s data_transfer

# Request resources on an Azure H100 node
srun -p h100 --ntasks=1 --mem=16G --cpus-per-task=10 --time=05:00:00 --pty bash

# Create the destination directory if it doesn't exist
mkdir -p /nfsdata/AITHYRA/shared/$USER/

# Now copy your data
cp -r /mnt/labs/home/$USER/my_dataset /nfsdata/AITHYRA/shared/$USER/

# Verify the copy
ls -lh /nfsdata/AITHYRA/shared/$USER/my_dataset

# Exit when complete (or detach with Ctrl+B, then D)
exit
```

4. **Run your computation:** Point your job to the Azure storage location. For heavy I/O use `/scratch` or `/netscratch`.
    
5. **Copy results back:** After completion, transfer important results to your home directory for long-term storage.
    

## Cluster Architecture & Resources

### Available Partitions

Partitions are resource pools for job submission. Always specify `--partition=<name>` (or `-p <name>`) in your job script.

|**Partition**|**Max Runtime**|**Nodes**|**Total Resources**|**Memory Default**|**Key Notes**|
|---|---|---|---|---|---|
|**`cpu`** (default)|4 days|login01|240 CPUs, 1440 GB RAM, 1.8 TB storage|4 GB per CPU|General CPU workloads. CPUs 0-15 reserved. On-premises.|
|**`gpu`**|4 days|gpu[01-02]|256 CPUs, 8× RTX 6000 GPUs, 1904 GB RAM|8 GB per CPU|RTX 6000 Ada (48GB VRAM). 4 GPUs/node. On-premises.|
|**`h100`**|4 days|H100Azure[01-10]|800 CPUs, 20× H100 NVL GPUs, 6450 GB RAM|8 GB per CPU|H100 NVL (94GB VRAM). 2 GPUs/node. Azure cloud.|
|**`spot`**|Varies|All nodes|Varies|8 GB per CPU|Special preemptible partition. Jobs may be killed/held.|

> **Memory Calculation:** Total memory = CPUs requested × Memory per CPU.
> 
> _Example:_ Requesting 16 CPUs in the `cpu` partition = 16 × 4 GB = 64 GB total memory.

### Azure H100 Partition: Important Considerations

The `h100` partition provides cutting-edge NVIDIA H100 NVL GPUs hosted on Microsoft Azure. These nodes are connected to the AITHYRA infrastructure via a high-speed network connection, which introduces network latency.

**Storage Performance Comparison (Azure Nodes):**

- **Very Slow:** `/mnt/labs/home` and `/mnt/labs/data` (On-premises NFS). Suitable only for job scripts, logging, and final result storage.
    
- **OK:** `/nfsdata/AITHYRA/shared` (Azure-local NFS). Optimized for high-throughput data operations. Use for dataset storage and intermediate results.
    
- **Fast:** `/netscratch` (BeeGFS shared filesystem). Low latency & high IOPS. RAID0—can go down anytime! Not reliable, only fast.
    
- **Fastest:** `/scratch` (Local NVMe on Azure VMs). Lowest latency, highest IOPS. Ideal for temporary data during job execution.
    

### Best Practices for Azure H100 Jobs

- **Data Preparation:** Copy large datasets to `/nfsdata/AITHYRA/shared/your_username/` before submitting jobs.
    
- **Job Execution:** Point your scripts to `/nfsdata/AITHYRA/shared/`. Save checkpoints here as well. For extreme I/O demands, copy data to `$SLURM_JOB_SCRATCH` within your job.
    
- **Result Management:** Store final results in `/nfsdata/AITHYRA/shared/` during the job, then copy critical results back to your home directory.
    

### When to Use Each Partition

- **`cpu`:** Data processing, compilation, non-GPU workflows, scripts.
    
- **`gpu`:** Deep learning training, rendering, visualization, moderate-scale AI models.
    
- **`h100`:** Large language models, large-scale deep learning, high-memory GPU workloads.
    
- **`spot`:** Preemptible workloads across all resources.
    

Bash

```
# Real-time cluster status commands
sinfo                                              # Quick overview
sinfo -p gpu --format="%P %n %c %m %G"             # Detailed GPU partition info
sinfo -p h100 --format="%P %n %c %m %G %O"         # H100 partition with CPU load
```

## Quality of Service (QOS) Levels

QOS levels control resource limits and job priorities. Select a QOS with `--qos=<name>`.

|**QOS**|**Priority**|**Allowed Partitions**|**Max Resources per User**|**Max Jobs**|**Max Array Tasks**|**Use Case**|
|---|---|---|---|---|---|---|
|**`debug`**|1000|cpu, gpu, h100|4 CPUs, 1 GPU, 32GB RAM|5|10|Quick testing (Max 1 hr limit)|
|**`high`**|500|cpu, gpu, h100|Unlimited|100|10,000|Urgent work (Auth required)|
|**`exclusive`**|300|cpu, gpu, h100|Max 3 full nodes|10|100|Dedicated node (Auth required)|
|**`normal`**|100|cpu, gpu, h100|160 CPUs, 4 GPUs, 1280GB RAM|100|10,000|Standard workloads (Default)|
|**`spot`**|10|spot|No limit|50|500|Preemptible workloads|

### Priority Guide & Key QOS Notes

- **Priority Order:** `debug` > `high` > `exclusive` > `normal` > `spot`.
    
- **Default:** `normal` is suitable for 95% of CPU and GPU workloads.
    
- **GPU Specification:** Always add `--gres=gpu:TYPE:N` when requesting GPUs (e.g., `--gres=gpu:rtx6000:2` or `--gres=gpu:h100nvl:1`).
    
- **Authorization:** Required for `high` and `exclusive` QOS. Email itservices@aithyra.ac.at.
    

## Choosing the Right Combination

### Decision Tree for Resource Selection

1. **Testing first?** Always use `--qos=debug`. Verify your script works before requesting larger resources.
    
2. **CPU-only tasks?** `--partition=cpu --qos=normal`.
    
3. **Need RTX 6000 GPUs?** `--partition=gpu --qos=normal --gres=gpu:rtx6000:N`.
    
4. **Need H100 NVL GPUs?** `--partition=h100 --qos=normal --gres=gpu:h100nvl:N` (Remember to prepare data in Azure storage first).
    
5. **Urgent deadline?** `--qos=high` (Requires authorization).
    
6. **Need a full dedicated node?** `--qos=exclusive --exclusive` (Requires authorization).
    

### Resource Sizing Best Practices

- **Start small:** Begin with 1-2 CPUs and 1 GPU.
    
- **Analyze actual usage:** Run a debug test and check consumption using `sacct -j <job_id> --format=JobID,MaxRSS,Elapsed,AllocCPUS`. Request 10-20% more than the actual usage.
    
- **I/O-intensive workloads:** Use `--tmp=200G` for fast local NVMe storage. Avoid over-requesting local storage or resources to reduce queue times.
    

## Running Jobs on the Cluster

### Interactive Sessions with `srun`

Perfect for debugging, development, and exploratory work. Direct SSH to compute nodes (e.g., `ssh gpu01`) only works if you have an active job on that node.

Bash

```
# Basic CPU session (4 CPUs, 16 GB RAM)
srun --ntasks=1 --cpus-per-task=4 --mem=16G --pty bash

# RTX 6000 GPU (1 GPU, 16 CPUs, 128 GB RAM)
srun -p gpu --gres=gpu:rtx6000:1 --ntasks=1 --cpus-per-task=16 --mem=128G --pty bash

# Quick testing with debug QOS (30 minutes)
srun -p gpu --qos=debug --gres=gpu:rtx6000:1 --time=30:00 --pty bash
```

### Batch Jobs with `sbatch`

Write a job script and submit it for long-running computations.

**Example 1: Basic CPU Job Script (`cpu_job.sh`)**

Bash

```
#!/bin/bash
#SBATCH --job-name=my_cpu_job           
#SBATCH --partition=cpu                 
#SBATCH --qos=normal                    
#SBATCH --ntasks=1                      
#SBATCH --cpus-per-task=8               
#SBATCH --mem=32G                       
#SBATCH --time=1-00:00:00               
#SBATCH --output=logs/job_%j.out        
#SBATCH --error=logs/job_%j.err         

echo "Job started on: $(date)"
cd $SLURM_SUBMIT_DIR
./my_cpu_program --input data.in --output results.out
echo "Job finished on: $(date)"
```

_Submit via:_ `mkdir -p logs && sbatch cpu_job.sh`

**Example 2: GPU Job with Local Scratch (`gpu_job.sh`)**

Bash

```
#!/bin/bash
#SBATCH --job-name=my_gpu_training
#SBATCH --partition=gpu
#SBATCH --qos=normal
#SBATCH --gres=gpu:rtx6000:1            
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16              
#SBATCH --mem=128G                      
#SBATCH --time=2-00:00:00               
#SBATCH --output=logs/gpu_job_%j.out
#SBATCH --error=logs/gpu_job_%j.err

SCRATCH_DIR="/scratch/${USER}_${SLURM_JOB_ID}"
mkdir -p "$SCRATCH_DIR"

# Stage data
cp $HOME/datasets/my_dataset.tar.gz $SCRATCH_DIR
cd $SCRATCH_DIR
tar -xzf my_dataset.tar.gz

# Run training
python3 /mnt/labs/home/$USER/scripts/train_model.py \
    --data_dir $SCRATCH_DIR/my_dataset \
    --output_dir $SCRATCH_DIR/results

# Copy back and cleanup
mkdir -p $HOME/results/job_$SLURM_JOB_ID
cp -r $SCRATCH_DIR/results/* $HOME/results/job_$SLURM_JOB_ID/
rm -rf "$SCRATCH_DIR"
```

**Example 3: H100 Azure Node Job (`h100_job.sh`)**

Bash

```
#!/bin/bash
#SBATCH --job-name=llm_training_h100
#SBATCH --partition=h100
#SBATCH --qos=normal
#SBATCH --gres=gpu:h100nvl:2            
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=40              
#SBATCH --mem=320G                      
#SBATCH --time=3-00:00:00               
#SBATCH --output=logs/h100_job_%j.out
#SBATCH --error=logs/h100_job_%j.err

# IMPORTANT: Ensure your data is in Azure-local storage BEFORE submitting
AZURE_DATA="/nfsdata/AITHYRA/shared/$USER"
DATASET_PATH="$AZURE_DATA/datasets/llm_training_data"
OUTPUT_PATH="$AZURE_DATA/results/job_$SLURM_JOB_ID"
mkdir -p $OUTPUT_PATH

if [ ! -d "$DATASET_PATH" ]; then
    echo "ERROR: Dataset not found. Copy data to Azure storage first!"
    exit 1
fi

python3 /mnt/labs/home/$USER/scripts/train_llm.py \
    --data_dir $DATASET_PATH \
    --output_dir $OUTPUT_PATH \
    --num_gpus 2

# Copy critical results back
cp $OUTPUT_PATH/final_model.pt /mnt/labs/home/$USER/models/job_${SLURM_JOB_ID}_model.pt
```

## Monitoring & Managing Your Jobs

### Job Queue Status (`squeue`)

Bash

```
squeue                  # View all jobs
squeue --me             # View only your jobs
squeue -p gpu           # View jobs in a specific partition
```

### Canceling Jobs (`scancel`)

Bash

```
scancel <job_id>        # Cancel a specific job
scancel -u $USER        # Cancel all your jobs
```

### Job History & Resource Usage (`sacct`)

Bash

```
# View recent jobs
sacct --starttime=$(date -d '1 day ago' +%Y-%m-%d)

# Detailed resource usage for a specific job
sacct -j <job_id> --format=JobID,JobName,Partition,State,Elapsed,MaxRSS,AllocCPUS
```

### Live Job Monitoring

Bash

```
watch -n 2 'squeue --me'       # Watch queue update every 2 seconds
tail -f logs/job_<job_id>.out  # View live output of a running job
```

> **Pro Tip:** After each test job with `--qos=debug`, run `sacct` to see how much memory and time you actually needed. Requesting the right amount of resources reduces queue times for everyone.

## Additional Resources & Next Steps

- **Slurm Official Documentation:** [https://slurm.schedmd.com/](https://slurm.schedmd.com/)
    
- **Module System Documentation:** Coming soon (Lmod-based)
    
- **Jump SSH Configuration Guide:** Detailed setup instructions
    
- **Need Help?** Contact itservices@aithyra.ac.at