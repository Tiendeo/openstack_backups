# Openstack backups

Openstack CLI wrapper written in Python for backups creation. The process is defined to create an image of the server a snapshots of the attached volumes.

## Create Image

./create-image.py - creates a snapshot of a selected server.

Required:  

```text
    -s, --server : Name of the target server/instance
```

Optional:  

```text
    -c, --cloud : Openstack cloud name to get configuration from clouds.yaml
    -r, --region : Openstack region where the server name is running
```

## Execute it

Example in docker file of a potential execution:

```yaml
version: '3'
services:
openstack:
    image: ismaelperal/openstack_backups:release-1.0.0
    volumes:
    - ~/clouds.yaml:/etc/openstack/clouds.yaml:ro
    command:
    - python
    - create-image.py
    - "-s"
    - MY_SERVER
    - "-c"
    - ovh
    - "-r"
    - GRA1
```
