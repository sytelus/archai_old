import copy
from typing import Optional

import torch
from torch.optim.optimizer import Optimizer
import numpy as np
from collections import defaultdict

from torch import nn, Tensor

from . import utils
from .common import get_logger, get_tb_writer

def cross_entropy_smooth(input:torch.Tensor, target, size_average=True, label_smoothing=0.1):
    # TODO: replace this with SmoothCrossEntropyLoss class
    y = torch.eye(10).to(input.device)
    lb_oh = y[target]

    target = lb_oh * (1 - label_smoothing) + 0.5 * label_smoothing

    logsoftmax = nn.LogSoftmax()
    if size_average:
        return torch.mean(torch.sum(-target * logsoftmax(input), dim=1))
    else:
        return torch.sum(torch.sum(-target * logsoftmax(input), dim=1))

class Metrics:
    """Record top1, top5, loss metrics, track best so far"""

    def __init__(self, epochs:int, tb_tag:Optional[str],
                 optim:Optional[Optimizer], logger_freq:int=10) -> None:
        self.top1 = utils.AverageMeter()
        self.top5 = utils.AverageMeter()
        self.loss = utils.AverageMeter()
        self.best_top1, self.best_epoch = 0., 0
        self.logger_freq = logger_freq
        self.optim, self.tb_tag = optim, tb_tag
        self.epoch, self.epochs = 0, 0
        self.step, self.global_step = 0, 0

    def pre_step(self, x:Tensor, y:Tensor):
        pass

    def post_step(self, x:Tensor, y:Tensor, logits:Tensor,
                  loss:Tensor, steps:int)->None:
        # update metrics after optimizer step
        batch_size = x.size(0)
        prec1, prec5 = utils.accuracy(logits, y, topk=(1, 5))
        self.loss.update(loss.item(), batch_size)
        self.top1.update(prec1.item(), batch_size)
        self.top5.update(prec5.item(), batch_size)
        self.step += 1
        self.global_step += 1

        self.report_cur(steps)

    def report_cur(self, steps:int):
        if self.logger_freq>0 and \
                (self.step % self.logger_freq==0 or self.step==steps-1):
            logger = get_logger()
            logger.info(
                f"Epoch: [{self.epoch+1:3d}/{self.epochs}] "
                f"Step {self.step:03d}/{steps:03d} "
                f"Loss {self.loss.avg:.3f} "
                f"Prec@(1,5) ({self.top1.avg:.1%},"
                f" {self.top5.avg:.1%})")
        if self.tb_tag:
            writer = get_tb_writer()
            writer.add_scalar(f'{self.tb_tag}/loss',
                              self.loss.avg, self.global_step)
            writer.add_scalar(f'{self.tb_tag}/top1',
                              self.top1.avg, self.global_step)
            writer.add_scalar(f'{self.tb_tag}/top5',
                              self.top5.avg, self.global_step)

    def report_best(self):
        if self.logger_freq>0:
            logger = get_logger()
            logger.info(f"Final best top1={self.best_top1}, "
                        f"epoch{self.best_epoch}")

    def pre_epoch(self):
        lr = self.get_cur_lr()
        if lr is not None:
            logger, writer = get_logger(), get_tb_writer()
            if self.logger_freq>0:
                logger.info(f"{self.tb_tag} {self.epoch+1}: LR {lr}")
            writer.add_scalar('{self.tb_tag}/lr', lr, self.global_step)

    def get_cur_lr(self)->Optional[float]:
        if self.optim is not None:
            return self.optim.param_groups[0]['lr']
        else:
            return None

    def post_epoch(self):
        self.epoch += 1
        self.step = 0

        if self.best_top1 < self.top1.avg:
            self.best_epoch = self.epoch
            self.best_top1 = self.top1.avg

        if self.logger_freq>0:
            logger = get_logger()
            logger.info(f"{self.tb_tag}: [{self.epoch:3d}/{self.epochs}] "
                        f"Final Prec@1 {self.top1.avg:.4%}")

    def is_best(self)->bool:
        return self.epoch == self.best_epoch

class Accumulator:
    # TODO: replace this with Metrics class
    def __init__(self):
        self.metrics = defaultdict(lambda: 0.)

    def add(self, key, value):
        self.metrics[key] += value

    def add_dict(self, dict):
        for key, value in dict.items():
            self.add(key, value)

    def __getitem__(self, item):
        return self.metrics[item]

    def __setitem__(self, key, value):
        self.metrics[key] = value

    def get_dict(self):
        return copy.deepcopy(dict(self.metrics))

    def items(self):
        return self.metrics.items()

    def __str__(self):
        return str(dict(self.metrics))

    def __truediv__(self, other):
        newone = Accumulator()
        for key, value in self.items():
            if isinstance(other, str):
                if other != key:
                    newone[key] = value / self[other]
                else:
                    newone[key] = value
            else:
                newone[key] = value / other
        return newone


class SummaryWriterDummy:
    def __init__(self, log_dir):
        pass

    def add_scalar(self, *args, **kwargs):
        pass
