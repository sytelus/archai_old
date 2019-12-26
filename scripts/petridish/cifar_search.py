from FastAutoAugment.nas.bilevel_arch_trainer import BilevelArchTrainer
from FastAutoAugment.common.common import common_init
from FastAutoAugment.nas.search_arch import search_arch
from FastAutoAugment.petridish.petridish_mutator import PetridishMutator

if __name__ == '__main__':
    conf = common_init(defaults_filepath='confs/defaults.yaml',
                       experiment_name='cifar_search')

    conf_common = conf['common']
    conf_data = conf['dataset']
    conf_search = conf['darts']['search']

    dag_mutator = PetridishMutator()
    arch_trainer = BilevelArchTrainer()
    found_model_desc = search_arch(conf_common, conf_data, conf_search,
                                   dag_mutator, arch_trainer)