from __future__ import print_function
#from .hcl2json import *
import hcl2json
import itertools
import json
import os
import re
import subprocess
import yaml

# Keep an eye on this PR as it would greatly simplify stuff
# https://github.com/hashicorp/hcl/pull/24/files

deployment_id = 'BaseStack'

TF_FILE = 'aws.tf.' + deployment_id
TF_STATE_FILE = 'aws.tfstate.' + deployment_id

filters = {}
filters[deployment_id] = {}
filters[deployment_id]['vpc-id'] = "vpc-fda45199"
filters[deployment_id]['tags.aws:cloudformation:stack-id'] = "BaseStack"
filters[deployment_id]['tags.aws_cloudformation_stack-id'] = "BaseStack"
filters[deployment_id]['tag-value'] = "BaseStack"

VPC_ID_FILTER = [{"name": "vpc-id", "values": [filters[deployment_id]['vpc-id']] }]
TAG_VALUE_FILTER = [{"name": "tag-value", "values": [filters[deployment_id]["tag-value"]] }]

VPC_FILTERABLE = ['igw', 'nac', 'rt', 'rta', 'sg', 'eip' ]
TAG_FILTERABLE = ['ec2','vpc','elb','igw','nac','nif','r53z','rt', 'rta', 'sg', 'sn']

if os.path.exists(TF_FILE):
    try:
        os.remove(TF_FILE)
    except OSError, e:
        print ("Error: %s - %s." % (e.filename,e.strerror))
        
if os.path.exists(TF_STATE_FILE):
    try:
        os.remove(TF_STATE_FILE)
    except OSError, e:
        print ("Error: %s - %s." % (e.filename,e.strerror))


resources = ["ec2","vpc","eip","elb","igw","nac","nif","r53r","r53z","rt","rta","sg","sn"]
resources = ["ec2","vpc"]


def _load_tfstate_resources(tfstate_file):
    '''
    @returns: list of dicts
    '''
    with open(tf_state_file, 'r') as f:
        contents = json.load(f)
    return contents['modules']

def get_tfstate_resources(tfstate):
    '''
    @param tfstate: terraforming tfstate string
    @returns: list of resource tuples (resource_name, resource_dict)
    '''
    tfstate = json.loads(tfstate)
    tfstate = tfstate['modules']
    resources = []
    for i,entry in enumerate(tfstate):
        if 'resources' in tfstate[i].keys():
            resources.append(tfstate[i]['resources'])
    return resources

def _load_tf_file(tf_file):
    '''
    Returns and array of resources from a terraform tf file
    '''
    with open(tf_file, 'r') as f:
        contents = f.read()
        resources = contents.split('\n\nresource')
    return resources

def get_tf_resources(tf):
    '''
    @param tf: string representing tf output from terraforming
    @returns: dict with keys (instance_name, type, resource, spec) 
              where instance_name is not quite unique instance name
                    type is in [resource, variable, module, provider]
                    class is the resource type
                    spec is the json dict of resource properties

    {'instance_name': 'eipalloc-531cd437', 'type': 'resource', 'class': 'aws_eip', 'spec': {u'instance': u'i-6590e5a2', u'vpc': True}}
    '''
    return hcl2json.parse_all_hcl_blocks(tf, entry_types=['resource'])


def get_resource_keyname(resource_entry):
    keyname = resource_entry['class'] + '.' + resource_entry['instance_name']
    return keyname


def build_filters(filters):
    for tag in config_block['filers']:
        


    for resource in config_bock['resources']:
        tf_filters = []
        if resource in VPC_FILTERABLE:
            tf_filters += VPC_ID_FILTER
        if resource in TAG_FILTERABLE:
            tf_filters += TAG_VALUE_FILTER
        if tf_filters:
            tf_filters = ["--filters", json.dumps(tf_filters) ]
        return tf_filters



# The great danger is having a resource entry for tf_state without the corresponding tf entry.
# In this case, terraform apply will match the tf_state to the tf file, i.e. delete the resource.
# We need to check that we never generate a tf entry without a corresponding tf_state entry.


    cmd = "terraforming {resource}".format(resource=resource)
    cmd = re.split('\s', cmd)
    if TF_FILTERS:
        cmd = cmd + TF_FILTERS
    print("tf cmd = ", cmd)
    tf = subprocess.check_output(cmd)

    tmpdir = "tftemp"
    if not os.path.exists(tmpdir):
        os.mkdir(tmpdir)
    path = os.path.join(tmpdir,resource + ".tf")
    with open(path,'w') as out:
        out.write(tf)

    #print("get_tf_resources(tf) ",get_tf_resources(tf))
    tf_resource_names = [ get_resource_keyname(x) for x in get_tf_resources(tf)]
    print("tf_resource_names = ", tf_resource_names)


    cmd = "terraforming {resource} --tfstate".format(resource=resource)
    cmd = re.split('\s', cmd)
    if TF_FILTERS:
        cmd = cmd + TF_FILTERS 
    print("tfstate cmd = ", cmd)
    tfstate = subprocess.check_output(cmd)
    tfstate_resources = get_tfstate_resources(tfstate)
    tfstate_resource_names = list(itertools.chain(*tfstate_resources))
    print("tfstate_resource_names = ",tfstate_resource_names)

    tfstate_minus_tf = set(tfstate_resource_names).difference(set(tf_resource_names))

    if tfstate_minus_tf:
        print("Warning, found resources in tfstate not in tf file.  Resources would be deleted")
        print("tfstate - tf = ", tfstate_minus_tf)
        #print("Use --force to allow resource deletion")

    tf_minus_tfstate = set(tf_resource_names).difference(set(tfstate_resource_names))
    if tf_minus_tfstate:
        print("Found items in tf not in tfstate.  They will be created")
        print("tf - tfstate = ", tf_minus_tfstate)

    # Finally write tfstate to file
    if not os.path.exists(TF_STATE_FILE):
        with open(TF_STATE_FILE, 'w') as f:
            f.write(tfstate)
    else:
        cmd = cmd +  ["--overwrite","--merge", TF_STATE_FILE ]
        tfstate = subprocess.check_output(cmd)

    print("")


def main():
    HAS_RUAML = False
    try:
        import ruaml.yaml as yaml
        HAS_RUAML = True
    except:
        import yaml

    parser = argparse.ArgumentParser(description="Parser for compose2marathon")
    parser.add_argument('--tf-out-dir', metavar='d', type=str,
                       help='output directory for tf files',
                       default="tf-files")
    parser.add_argument('--tfstate-out-dir',
                       default="tfstate-files",
                       help='output directory for tfstate files')
    parser.add_argument('--filter-config',
                       default="filter-config.yml",
                       help='see example at http://github.com/kbroughton/terraforming.git/filter-config.yml')
    parser.add_argument('--tf-source',
                       default=None,
                       help='file or dir with .tf files used as source instead of terraforming against provider')
    parser.add_argument('--tfstate-source',
                       default=None,
                       help='file or dir with .tfstate files used as source instead of terraforming against provider')

    args = parser.parse_args()

    filter_configs = default_config()
    with open(args.filter_config, 'r') as f:
        filter_configs = filter_configs.update(yaml.load(f)['filter_configs'])



# Filter candidates
# ec2 tenancy default / dedicated
# vpc id vpc-fda45199 / vpc-6b32e00f
# igw vpc_id
# nac vpc_id
# nif tags 
# r53r zone_id, id, name  
# r53z vpc_id, tags, zone_id     
# rt vpc_id, tags
# rta vpc_id, tags
# sg vpc_id, tags
