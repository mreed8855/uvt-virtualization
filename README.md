# uvt-virtualization
Test kvm using uvtool
uvtvirt.py
usage: uvtvirt.py [-h] [-i IMAGE] [--debug] [-l LOG_FILE]

Run uvt-kvm with defaults
uvtvirt.py --debug

Specify a location for uvt-simplestreams-libvirt to retrive an image
uvtvirt.py -i http://cloud-images.ubuntu.com/daily/server/daily/

Specify a cloud image for uvt-kvm create to create a vm

uvtvirt.py -i file:///home/ubuntu/focal-server-cloudimg-amd64.img
