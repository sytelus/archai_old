from typing import Tuple, Any, Iterable, Optional
import  torch.nn as nn
import torch
from torch.optim.optimizer import Optimizer
from  torch.utils.data import DataLoader
import os
import yaml

from ..common.config import Config
from .model import Model
from .arch import Arch
from ..common.data import get_dataloaders
from ..common.common import get_logger, get_tb_writer
from ..common import utils
from ..common.optimizer import get_lr_scheduler, get_optimizer, get_lossfn
from .vis_genotype import draw_model_desc
from ..common.train_test_utils import train_test
from .model_desc import ModelDesc

def search_arch(conf:Config, model_desc:ModelDesc)->None:
    logger = get_logger()

    # region conf vars
    conf_search   = conf['darts']['search']
    conf_loader   = conf['darts']['search']['loader']
    conf_ds       = conf['dataset']
    conf_w_opt    = conf_search['weights']['optimizer']
    conf_w_sched  = conf_search['weights']['lr_schedule']
    ds_name       = conf_ds['name']
    max_batches     = conf_ds['max_batches']
    conf_lossfn   = conf_search['lossfn']
    dataroot      = conf['dataroot']
    aug           = conf_loader['aug']
    cutout        = conf_loader['cutout']
    val_ratio     = conf_loader['val_ratio']
    batch_size    = conf_loader['batch']
    epochs        = conf_loader['epochs']
    val_fold      = conf_loader['val_fold']
    n_workers     = conf_loader['n_workers']
    horovod       = conf['horovod']
    report_freq   = conf['report_freq']
    grad_clip     = conf_w_opt['clip']
    plotsdir      = conf['plotsdir']
    chkptdir      = conf['chkptdir']
    data_parallel     = conf_search['data_parallel']
    # endregion

    # get data
    train_dl, val_dl, *_ = get_dataloaders(
        ds_name, batch_size, dataroot,
        aug=aug, cutout=cutout, load_train=True, load_test=False,
        val_ratio=val_ratio, val_fold=val_fold, horovod=horovod,
        max_batches=max_batches, n_workers=n_workers)

    device = torch.device('cuda')

    lossfn = get_lossfn(conf_lossfn, conf_ds).to(device)

    model = Model(model_desc)
    logger.info("Total param size = %f MB", utils.param_size(model))
    if data_parallel:
        model = nn.DataParallel(model).to(device)
    else:
        model = model.to(device)

    # trainer for alphas
    arch = Arch(conf, model, lossfn)

    # optimizer for w
    w_optim = get_optimizer(conf_w_opt, model.weights())
    lr_scheduler = get_lr_scheduler(conf_w_sched, epochs, w_optim)

    # in search phase we typically only run 50 epochs
    best_model_desc:Optional[ModelDesc] = None
    valid_iter:Optional[Iterable[Any]] = None
    def _pre_epoch(*_):
        nonlocal valid_iter
        valid_iter = iter(val_dl)

    def _post_epochfn(epoch, best_top1, top1, is_best):
        nonlocal best_model_desc

        # log results of this epoch
        model_desc = model.finalize(max_edges=2) # TODO: add config max_edges
        logger.info("model_desc = {}".format(model_desc))
        # model_desc as a image
        plot_filepath = os.path.join(plotsdir, "EP{:03d}".format(epoch+1))
        caption = "Epoch {}".format(epoch+1)
        draw_model_desc(model_desc, plot_filepath+"-normal", caption=caption)

        if is_best or best_model_desc is None:
            best_model_desc = model_desc

    def _pre_stepfn(step, x_train, y_train, cur_lr):
        nonlocal valid_iter
        # reset val loader if we exausted it
        try:
            x_val, y_val = next(valid_iter)
        except StopIteration:
            # reinit iterator
            valid_iter = iter(val_dl)
            x_val, y_val = next(valid_iter)
        x_val, y_val = x_val.to(device), y_val.to(device, non_blocking=True)

        # update alphas
        arch.step(x_train, y_train, x_val, y_val, cur_lr, w_optim)

    train_test(train_dl, val_dl, model, device, lossfn, lossfn,
        w_optim, aux_weight=0.0, grad_clip=grad_clip, lr_scheduler=lr_scheduler,
        drop_path_prob=0.0, model_save_dir=chkptdir, report_freq=report_freq,
        epochs=epochs, pre_stepfn=_pre_stepfn, pre_epochfn=_pre_epoch,
        post_epochfn=_post_epochfn)

    logger.info("Best architecture\n{}".format(yaml.dump(best_model_desc)))

    return best_model_desc

