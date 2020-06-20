"""
定义VMManage数据模型
"""
import datetime
import logging
from django.db import models

views_logger = logging.getLogger("galilee")

class Vminfo(models.Model):
    vmname = models.CharField(max_length=50)
    cpus = models.PositiveSmallIntegerField()
    memorys = models.PositiveSmallIntegerField()
    instanceUuid = models.CharField(max_length=40, unique=True)
    disk = models.PositiveSmallIntegerField(blank=True)
    cn = models.CharField(max_length=25, blank=True, default='00000000000')
    os = models.CharField(max_length=40, blank=True, default='unknow')
    hostname = models.CharField(max_length=50, blank=True, default='unknow')
    ip = models.GenericIPAddressField(protocol='both', null=True)
    update_time = models.DateTimeField(auto_now_add=True)
    dead_time = models.DateField(default=datetime.date.today()+datetime.timedelta(weeks=52))
    user = models.IntegerField(blank=True, null=True)
