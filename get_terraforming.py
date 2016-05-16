from __future__ import print_function
import argparse
import hcl2json
import itertools
import json
import os
import re
import shutil
import subprocess
import yaml

# Keep an eye on this PR as it would greatly simplify stuff
# https://github.com/hashicorp/hcl/pull/24/files



VPC_FILTERABLE = ['igw', 'nac', 'rt', 'rta', 'sg', 'eip' ]
TAG_FILTERABLE = ['ec2','vpc','elb','igw','nac','nif','r53z','rt', 'rta', 'sg', 'sn']

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


def build_filters(filters, resource):
    '''
    @param filters: filters from filter-config.yml
    @param resource: the resource in question
    @returns ["--filters", stringified_filters_in_aws_format]
    '''
    tf_filters = []
    print("filters['vpc-id']", filters['vpc-id'])
    for key, val in filters.iteritems():
        if (resource in VPC_FILTERABLE ) and (key == 'vpc-id'):
            print("VPC_ID_FILTER")
            if resource == 'vpc':
                VPC_ID_FILTER = [{"name": "id", "values": filters['vpc-id'] } ]
            else:
                VPC_ID_FILTER = [{"name": "vpc-id", "values": filters['vpc-id'] } ]
            tf_filters += VPC_ID_FILTER
        if (resource in TAG_FILTERABLE) and (key == 'tag-value'):
            TAG_VALUE_FILTER = [{"name": "tag-value", "values": filters["tag-value"] }]
            tf_filters += TAG_VALUE_FILTER
        
    if tf_filters:
        print("build_filters for {}".format(resource), tf_filters)
    tf_filters = ["--filters", json.dumps(tf_filters) ]
    return tf_filters



# The great danger is having a resource entry for tf_state without the corresponding tf entry.
# In this case, terraform apply will match the tf_state to the tf file, i.e. delete the resource.
# We need to check that we never generate a tf entry without a corresponding tf_state entry.

def generate_artifacts(filter_config):

    resources = filter_config['resources']
    filters = filter_config['filters']
    deployment_id = filter_config['deployment_id']
    output_root_dir = filter_config['output_root_dir']

    TF_FILE = 'aws.tf.' + deployment_id
    TF_STATE_FILE = 'aws.tfstate.' + deployment_id

    tf_dir = os.path.join(output_root_dir,'tf_files')
    if os.path.exists(tf_dir):
        try:
            shutil.rmtree(tf_dir)
        except OSError, e:
            print ("Error: %s - %s." % (e.filename,e.strerror))   
    os.mkdir(tf_dir)

    tf_path = os.path.join(output_root_dir,TF_FILE)     
    tf_state_path = os.path.join(output_root_dir,TF_STATE_FILE)     

    if os.path.exists(tf_state_path):
        try:
            os.remove(tf_state_path)
        except OSError, e:
            print ("Error: %s - %s." % (e.filename,e.strerror))

    tf_all = ""
    for resource in resources:
        cmd = "terraforming {resource}".format(resource=resource)
        cmd = re.split('\s', cmd)
        resource_filters = build_filters(filters, resource)
        if resource_filters:
            cmd = cmd + resource_filters
        print("tf cmd = ", cmd)
        tf = subprocess.check_output(cmd)

        path = os.path.join(tf_dir, resource + ".tf")
        with open(path,'w') as f:
            f.write(tf)
        tf_all = "\n\n".join([tf_all, tf])

        #print("get_tf_resources(tf) ",get_tf_resources(tf))
        tf_resource_names = [ get_resource_keyname(x) for x in get_tf_resources(tf)]
        print("tf_resource_names = ", tf_resource_names)


        cmd = "terraforming {resource} --tfstate".format(resource=resource)
        cmd = re.split('\s', cmd)
        if resource_filters:
            cmd = cmd + resource_filters 
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
        if not os.path.exists(tf_state_path):
            with open(tf_state_path, 'w') as f:
                f.write(tfstate)
        else:
            cmd = cmd +  ["--overwrite","--merge", tf_state_path ]
            tfstate = subprocess.check_output(cmd)

        print("")
    
    with open(tf_path, 'w') as f:
        f.write(tf_all)


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
    parser.add_argument('--filter-config-file',
                       default="filter-config.yml",
                       help='see example at http://github.com/kbroughton/terraforming.git/filter-config.yml')
    parser.add_argument('--tf-source',
                       default=None,
                       help='file or dir with .tf files used as source instead of terraforming against provider')
    parser.add_argument('--tfstate-source',
                       default=None,
                       help='file or dir with .tfstate files used as source instead of terraforming against provider')

    args = parser.parse_args()



    filter_config = {}
    # set default config values
    filter_config['resources'] = resources

    with open(args.filter_config_file, 'r') as f:
        loaded_config = yaml.safe_load(f)['filter_config']
        print("loaded_config", loaded_config)
        filter_config.update(loaded_config)

    output_root_dir = os.path.dirname(args.filter_config_file)
    filter_config['output_root_dir'] = output_root_dir

    print("filter_config", filter_config)
    generate_artifacts(filter_config)


if __name__ == '__main__':
    main()

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
