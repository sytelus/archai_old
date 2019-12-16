
from FastAutoAugment.common.common import common_init
from FastAutoAugment.darts.test import test_arch

if __name__ == '__main__':
    conf = common_init(config_filepath='confs/imagenet_darts.yaml',
        defaults_filepath='confs/defaults.yaml')

    test_arch(conf)