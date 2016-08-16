set -o errexit -o nounset -o pipefail
unset HISTFILE

# Root directories for source and target (Default to same machine)
TARGETROOT=""
SRCROOT=""

# Prepare target directory configuration
DST_USERSPACE_DIR="${TARGETROOT}/usr"
DST_USERSPACE_LOCAL_DIR="${TARGETROOT}/usr/local"
DST_BOOT_DIR="${TARGETROOT}/boot"
DST_ETC_DIR="${TARGETROOT}/etc"
TEMP_DIR="/tmp"

# If we only need to prepare, do clean-ups and reboot
if [ "$1" == "prepare" ]; then

  # Disable nouveau from kernel cmdline
  echo ">>> Blacklisting nouveau driver through GRUB"
  sed -r -i 's/^(GRUB_CMDLINE_LINUX=.*)"$/\1 rd.driver.blacklist=nouveau nouveau.modeset=0"/' \
    /etc/default/grub

  # Update GRUB
  grub2-mkconfig -o /boot/grub2/grub.cfg

  # Shutdown
  echo ">>> Rebooting instance"
  sync
  nohup sh -c 'kill $(pidof sshd); reboot' </dev/null >/dev/null 2>&1 &
  sleep 60
  exit 0
fi

# Get cuda bucket to use from command-line
NVIDIA_VERSION=$1

# The nVidia driver files to download and install
NVIDIA_KERNEL_DRIVER_URL="https://s3-us-west-2.amazonaws.com/dcos-nvidia-drivers/${NVIDIA_VERSION}-Linux-x86_64/nvidia.run"
NVIDIA_GPU_GDK_URL="https://s3-us-west-2.amazonaws.com/dcos-nvidia-drivers/${NVIDIA_VERSION}-Linux-x86_64/gdk.run"
NVIDIA_CUDA_URL="https://s3-us-west-2.amazonaws.com/dcos-nvidia-drivers/${NVIDIA_VERSION}-Linux-x86_64/cuda.run"
NVIDIA_CUDNN_URL="https://s3-us-west-2.amazonaws.com/dcos-nvidia-drivers/${NVIDIA_VERSION}-Linux-x86_64/cudnn.tgz"
#
# WARNING: Some nVidia's hard-links will require authorization, making
#          the link impossible to use. On production, please downoad all
#          these files to a separate directory first.

echo ">>> Removing nouveau module from kernel..."
rmmod nouveau

# Get the kernel to install packages for
KERNEL=$(uname -r)

# Install missing dependencies
echo ">>> Installing required packages to build for kernel ${KERNEL}..."
yum install -y kernel-devel-${KERNEL} kernel-headers-${KERNEL} gcc make pciutils

# Prepare kernel-specific directories
DST_KERNEL_DIR="${TARGETROOT}/lib/modules/${KERNEL}/kernel/drivers/video"
SRC_KERNEL_DIR="${SRCROOT}/lib/modules/${KERNEL}/build"

# Crawl latest URL from here: http://www.nvidia.com/Download/index.aspx?lang=en-us
echo ""
echo ">>> Downloading nvidia kernel modules..."
curl -s ${NVIDIA_KERNEL_DRIVER_URL} > ${TEMP_DIR}/NVIDIA-kernel.run
chmod +x ${TEMP_DIR}/NVIDIA-kernel.run

echo ">>> Installing nvidia kernel modules..."
${TEMP_DIR}/NVIDIA-kernel.run \
  --accept-license \
  --no-questions \
  --ui=none \
  --disable-nouveau \
  --utility-prefix=${DST_USERSPACE_DIR} \
  --documentation-prefix=${DST_USERSPACE_DIR} \
  --application-profile-path=${DST_USERSPACE_DIR}/share/nvidia \
  --kernel-source-path=${SRC_KERNEL_DIR} \
  --kernel-install-path=${DST_KERNEL_DIR} \
  --kernel-name=${KERNEL}

# Crawl latest URL from here: https://developer.nvidia.com/gpu-deployment-kit
echo ""
echo ">>> Downloading nvidia GPU GDK..."
curl -s ${NVIDIA_GPU_GDK_URL} > ${TEMP_DIR}/NVIDIA-gdk.run
chmod +x ${TEMP_DIR}/NVIDIA-gdk.run

echo ">>> Installing nvidia GPU GDK..."
${TEMP_DIR}/NVIDIA-gdk.run \
  --silent \
  --installdir=${TARGETROOT}/

# Crawl latest URL from here: https://developer.nvidia.com/cuda-downloads
echo ""
echo ">>> Downloading CUDA..."
curl -s ${NVIDIA_CUDA_URL} > ${TEMP_DIR}/NVIDIA-cuda.run
chmod +x ${TEMP_DIR}/NVIDIA-cuda.run

echo ">>> Installing CUDA..."
${TEMP_DIR}/NVIDIA-cuda.run \
  --silent \
  --kernel-source-path=${SRC_KERNEL_DIR} \
  --toolkit \
  --toolkitpath=${DST_USERSPACE_LOCAL_DIR}


# Crawl latest URL from here:
echo ""
echo ">>> Downloading cuDNN..."
curl -s ${NVIDIA_CUDNN_URL} > ${TEMP_DIR}/NVIDIA-cudnn.tgz

echo ">>> Installing cuDNN..."
tar -C ${DST_USERSPACE_DIR} --strip-components=1 -zxf ${TEMP_DIR}/NVIDIA-cudnn.tgz

echo ">>> Installing nVidia boot scripts..."
cat <<"EOF" > /usr/local/sbin/start-nvidia-drivers.sh
#!/bin/bash

start() {
  /sbin/modprobe nvidia
  if [ "$?" -eq 0 ]; then
    # Count the number of NVIDIA controllers found.
    NVDEVS=`lspci | grep -i NVIDIA`
    N3D=`echo "$NVDEVS" | grep "3D controller" | wc -l`
    NVGA=`echo "$NVDEVS" | grep "VGA compatible controller" | wc -l`
    N=`expr $N3D + $NVGA - 1`
    for i in `seq 0 $N`; do
      mknod -m 666 /dev/nvidia$i c 195 $i
    done
    mknod -m 666 /dev/nvidiactl c 195 255
  else
    exit 1
  fi
  /sbin/modprobe nvidia-uvm
  if [ "$?" -eq 0 ]; then
    # Find out the major device number used by the nvidia-uvm driver
    D=`grep nvidia-uvm /proc/devices | awk '{print $1}'`
    mknod -m 666 /dev/nvidia-uvm c $D 0
  else
    exit 1
  fi
}

stop() {
  /sbin/rmmod nvidia
  /sbin/rmmod nvidia-uvm
  rm -f /dev/nvidia*
}

case $1 in
  start|stop) "$1" ;;
esac
EOF
chmod 0755 /usr/local/sbin/start-nvidia-drivers.sh

# Create service
cat <<"EOF" > /etc/systemd/system/nvidia.service
[Unit]
Description=Load nVidia kernel drivers and populate devices

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/start-nvidia-drivers.sh start
ExecStop=/usr/local/sbin/start-nvidia-drivers.sh stop
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

# Register service
echo ">>> Enabling nVidia service"
systemctl enable nvidia.service

# Clean-up
echo ">>> Remove temporary files"
rm ${TEMP_DIR}/NVIDIA-kernel.run
rm ${TEMP_DIR}/NVIDIA-gdk.run
rm ${TEMP_DIR}/NVIDIA-cuda.run
rm ${TEMP_DIR}/NVIDIA-cudnn.tgz
rm -rf /tmp/* /var/tmp/*
rm /usr/local/sbin/install_nvidia.sh

echo ">>> Cleaning up SSH host keys"
shred -u /etc/ssh/*_key /etc/ssh/*_key.pub

echo ">>> Cleaning up accounting files"
rm -f rm -f /var/run/utmp
>/var/log/lastlog
>/var/log/wtmp
>/var/log/btmp

echo ">>> Remove temporary files"
rm -rf /tmp/* /var/tmp/*

echo ">>> Remove ssh client directories"
rm -rf /home/*/.ssh /root/.ssh

echo ">>> Remove history"
rm -rf /home/*/.*history /root/.*history
