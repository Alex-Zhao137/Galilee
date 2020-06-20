#!/usr/bin/env python
# -*- coding=utf-8 -*-
'''
@Author: your name
@Email: zhaoliang@hupu.com
@Date: 2020-06-08 15:22:11
@LastEditTime: 2020-06-19 18:20:27
@LastEditors: your name
@Description: VMManage视图
@FilePath: /Galilee/vmmanage/views.py
@可以输入预定的版权声明、个性签名、空行等
'''
import logging
from rest_framework import viewsets
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from pyVmomi import vim   # pylint: disable=no-name-in-module
from vmmanage.serializers import VminfoSerializer
from vmmanage.models import Vminfo
from vmmanage.utils.opt_vc import VirtualNet, OptVM


views_logger = logging.getLogger("galilee")

class VminfoViewSet(viewsets.ModelViewSet):
    """ 虚拟机信息视图集合 """
    queryset = Vminfo.objects.all().order_by('id')
    serializer_class = VminfoSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(methods=['post'], detail=False, permission_classes=[permissions.IsAuthenticated])
    def sync_vm(self, request, *args, **kwargs):
        """ 将vCenter中的虚拟机信息同步到系统 """
        args = request.data
        views_logger.info(args)
        query, status = Vminfo.objects.get_or_create(instanceUuid=args['instanceUuid'], defaults=args)
        views_logger.info("系统同步到VM信息 name:%s - %s", query.vmname, status)
        ser = self.get_serializer(query)
        return Response(ser.data)

    def create(self, request, *args, **kwargs):
        # test = OptVM("ceshi")
        # print(test.del_virtual_device(opt_obj='nic', obj_number=2))
        test = OptVM('MOD_CentOS_6.9_x64')
        print(test.deploy_vm(cpus=2, memory_gb=4, annotation="ceshi", network='10.64.60-vlan1060-PersonTest', disk_size=50, vm_name='ceshi', cluster='System-Testing', custom_spec='CentOS', hostname='ceshi'))
        return Response("ceshi")

    def destroy(self, request, *args, **kwargs):
        test = OptVM("ceshi")
        print(test.powerchange_vm("OFF"))
        print(test.del_vm())
        return Response("ceshi")

    def update(self, request, *args, **kwargs):
        return Response("ceshi")

    def partial_update(self, request, *args, **kwargs):
        return Response("ceshi")
