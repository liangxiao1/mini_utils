#!/bin/bash
#this tool setup local kvm host for running dva ci job
guest_name=kvm_aws
image_file=/home/dva_job/Fedora-Cloud-Base-31-1.9.x86_64_dva.qcow2
get_token(){
    token_file="token_tmp.txt"
    if [[ -e $token_file ]]; then
        rm -rf $token_file
    fi
    echo "Please enter directly to skip region if no test required!"
    echo "virt-qe has account access to aws, but no aws-us-gov and aws-china access."
    echo "aws-us-gov access key:"
    read USGOV_ACCESS_KEY
    echo "aws-us-gov secrete key:"
    read USGOV_SECRETE_KEY
    echo "aws-china access key:"
    read CHINA_ACCESS_KEY
    echo "aws-china secrete key:"
    read CHINA_SECRETE_KEY
    echo "aws access key:"
    read DEV_ACCESS_KEY
    echo "aws secrete key:"
    read DEV_SECRETE_KEY
    if [[ $USGOV_ACCESS_KEY != "" && $USGOV_SECRETE_KEY != "" ]];then
        echo "USGOV_ACCESS_KEY=$USGOV_ACCESS_KEY" >> $token_file
        echo "USGOV_SECRETE_KEY=$USGOV_SECRETE_KEY" >> $token_file
    fi
    if [[ $CHINA_ACCESS_KEY != "" && $CHINA_SECRETE_KEY != "" ]];then
        echo "CHINA_ACCESS_KEY=$CHINA_ACCESS_KEY" >> $token_file
        echo "CHINA_SECRETE_KEY=$CHINA_SECRETE_KEY" >> $token_file
    fi
    if [[ $DEV_ACCESS_KEY != "" && $DEV_SECRETE_KEY != "" ]];then
        echo "DEV_ACCESS_KEY=$DEV_ACCESS_KEY" >> $token_file
        echo "DEV_SECRETE_KEY=$DEV_SECRETE_KEY" >> $token_file
    fi
}
check_pkg(){
    for pkg in $@; do
        rpm -q  $pkg > /dev/null 2>&1
        if (( $? > 0 )); then
            echo "$pkg not installed, will install it"
            yum install -y $pkg
        else
            echo "$pkg installed already"
        fi
    done
}
LOCALNIC='eth0'
get_net(){
    nics=$(ip link|awk -F':' '{print $2}')
    for nic in $nics; do
        ip addr show $nic > /dev/null 2>&1
        if (( $? != 0 ));then
            continue
        fi
        ip addr show $nic|grep dynamic > /dev/null 2>&1
        if(( $? == 0 ));then
            echo "Found local net $nic"
            LOCALNIC=$nic
        fi
    done
}
get_token
get_net
branch=$(uname -r)
if [[ $branch =~ "el7" ]]; then
    echo "running on el7"
    rpm -Uvh https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm
    check_pkg qemu-system-x86 libvirt qemu-kvm virt-install libguestfs-tools
    systemctl enable libvirtd
    systemctl start libvirtd

fi
if [[ $branch =~ "el8" || $branch =~ "fc" ]]; then
    echo "running on el8 or fedora"
    check_pkg libvirt qemu-kvm virt-install libguestfs-tools
    systemctl enable libvirtd 
    systemctl start libvirtd
fi
for i in {1..5}; do
    virsh dominfo $guest_name > /dev/null 2>&1
    if (( $? == 0 )); then
        echo "kvm_aws exists, shutdown it!"
        virsh shutdown $guest_name
        virsh undefine $guest_name
    elif (( $? > 0 )); then
        echo "$guest_name down."
        break
    fi
    sleep 5
done
if [[ -e $token_file ]]; then
    echo "Copy token to image......"
    virt-customize -a $image_file --copy-in token_tmp.txt:/home
fi

echo "Start $guest_name guest......"
virt-install --name $guest_name --memory 2048 --vcpus 2 --disk $image_file \
--import --os-variant fedora-unknown --console pty,target_type=serial --network type=direct,source=$LOCALNIC,source_mode=bridge,model=virtio --noautoconsole
if (( $? == 0 )); then
    echo "Please use virsh console $guest_name to login"
    echo "Access new jenkins from vm ip: http://vmip:8080"
else
    echo "Failed to start $guest_name"
fi
 