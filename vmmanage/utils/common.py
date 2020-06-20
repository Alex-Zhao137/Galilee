#!/usr/bin/env python
# -*- coding=utf-8 -*-
'''
@Author: ZhaoLiang
@Email: zhaoliang@hupu.com
@Date: 2020-06-08 16:06:03
@LastEditTime: 2020-06-19 15:26:22
@LastEditors: your name
@Description: 和VC交互的上下文管理和类装饰器
@FilePath: /Galilee/vmmanage/utils/common.py
@可以输入预定的版权声明、个性签名、空行等
'''

# import types
import random
import logging
from math import trunc
from string import ascii_lowercase as allow_string
from string import digits as allow_digits
from functools import wraps
from pyVim.connect import SmartConnectNoSSL, Disconnect
from django.conf import settings



from pyVmomi import vim  #pylint: disable=no-name-in-module

vm_logger = logging.getLogger('optVm')

def get_default_setting(name):
    '''
    @description: 获取settings文件中的配置
    @return: 返回字典或者字符串
    '''
    settings_dict = getattr(settings, 'VMMANGE', {})
    if isinstance(name, list):
        return {key: settings_dict[key] for key in name}
    return settings_dict[name]

def get_vm_default_power_status():
    '''
    @description: 获取settings文件中的默认虚拟机电源状态
    @return: 返回OFF or ON
    '''
    return get_default_setting('VM_POWERON')

def get_random_vm_name():
    prefix = get_default_setting('VM_HOSTNAME_PREFIX')
    random_string = ''.join(random.sample(allow_string + allow_digits, 7))
    return perfix + "-" +  random_string

def get_dns_settings():
    return get_default_setting('DNS')

class SmartConnectionNoSSL(object):
    """
    创建用于VC连接的上下文管理器
    """
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.content = None
        self.service_instance = None

    def __enter__(self):
        self.service_instance = SmartConnectNoSSL(*self.args, **self.kwargs)
        return self.service_instance

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
        # if self.service_instance:
        #     Disconnect(self.service_instance)
        #     self.content = None
        #     self.service_instance = None

class LoginVC():
    """ 利用类装饰器封装上下文管理器和VC进行交互 """
    def __init__(self, need_content=False, need_si=False):
        self.vc = get_default_setting(['HOST', 'USERNAME', 'PASSWORD'])
        self.need_content = need_content
        self.need_si = need_si
        self.service_instance = None
        self.content = None

    def __call__(self, func):
        @wraps(func)
        def warpped_function(*args, **kwargs):
            with SmartConnectionNoSSL(host=self.vc['HOST'], user=self.vc['USERNAME'], pwd=self.vc['PASSWORD']) as si:
                self.service_instance = si
                self.set_content()
                if self.need_content:
                    kwargs['content'] = self.content
                if self.need_si:
                    kwargs['service_instance'] = self.service_instance
                result = func(*args, **kwargs)
            return result
        return warpped_function

    def set_content(self):
        self.content = self.service_instance.RetrieveContent()

def wait_for_task(task, msg):
    """ wait for a vCenter task to finish """
    vm_logger.info("TASK_ID: %s, NAME: %s", task.info.key, msg)
    while True:
        if task.info.state == 'success':
            vm_logger.info("TASK: %s, SUCCESS", msg)
            return True, task.info.state
        if task.info.state == 'error':
            vm_logger.error("TASK: %s, 出现错误", msg)
            vm_logger.error(task.info.description)
            return False, task.info.error.msg

@LoginVC(need_content=True)
def get_obj(vimtype, name, content=None):
    '''
    @description: 通过名字过去管理对象MOB
    @param {type} vimtype:[vim.ClusterComputeResource], [vim.VirtualMachine], [vim.ComputeResource]
    [vim.Datastore], [vim.HostSystem], [vim.dvs.DistributedVirtualPortgroup], [vim.Network], [vim.Datacenter]
    @link: 其他可以查询的管理对象查看 https://code.vmware.com/apis/968/vsphere
    @return: 如果查找到MOB，返回当前对象，没有找到，返回None
    '''
    obj = None
    vm_logger.info("查找 MOB vimtype: %s name:%s", vimtype, name)
    container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
    for i in container.view:
        if i.name == name:
            obj = i
            break
    container.Destroy()
    return obj

@LoginVC(need_content=True)
def get_obj_by_uuid(uuid, content=None):
    return content.searchIndex.FindAllByUuid(None, uuid, True, True)

# @LoginVC
# def get_obj_by_name(name, isVM=True, content=None):
#     return content.searchIndex.FindAllByDnsName(None, name, isVM)

@LoginVC(need_content=True)
def get_all_obj(vimtype, content=None):
    obj = None
    vm_logger.info("查找OBJ类 type:%s", str(vimtype))
    container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
    obj = container.view
    container.Destroy()
    return obj

@LoginVC(need_content=True)
def get_storage(cluster, useSpace, content=None):
    datastores = cluster.datastore
    datastore_list = [datastore.name for datastore in datastores if "vsan" in datastore.name and trunc(datastore.info.freeSpace/1024/1024/1024) > useSpace+170]
    if datastore_list:
        vm_logger.info("当前可供选择的存储列表 %s", datastore_list)
        return get_obj([vim.Datastore], random.choice(datastore_list))
    else:
        vm_logger.warning("没有可用存储空间 cluster:%s", cluster.name)
        return False

def get_mob_type(sort_name):
    mob_set = {
        "dvs_portgroup": vim.dvs.DistributedVirtualPortgroup,
        "network": vim.Network,
        }
    if sort_name in mob_set:
        return mob_set[sort_name]

@LoginVC(need_content=True)
def get_custom_spec(custom_spec, ip, hostname, content=None):
    guest_customization_spec = content.customizationSpecManager.GetCustomizationSpec(name=custom_spec)
    guest_spec = guest_customization_spec.spec
    if ip:
        adaptermap = vim.vm.customization.AdapterMapping()
        adaptermap.adapter = vim.vm.customization.IPSettings(ip=vim.vm.customization.FixedIp(ipAddress=str(ip.ip)), subnetMask=str(ip.netmask), gateway=str(list(ip)[1]))
        guest_spec.nicSettingMap = [adaptermap]
    globalip = vim.vm.customization.GlobalIPSettings(dnsServerList=get_dns_settings())
    hostname = vim.vm.customization.FixedName(name=hostname)
    guest_spec.globalIPSettings = globalip
    guest_spec.identity.hostName = hostname
    return guest_spec

def get_obj_prefix_label(language, obj):
    if obj == 'nic':
        language_prefix_label_mapper = {
            'English': 'Network adapter ',
            'Chinese': '网络适配器 '
        }
    if obj == 'disk':
        language_prefix_label_mapper = {
            'English': 'Hard disk ',
            'Chinese': '硬盘 '
        }
    return language_prefix_label_mapper.get(language)

# @LoginVC(need_si=True)
# def get_custom_info(obj, attr, mob_type, service_instance=None):
#     mob_type = get_mob_type(mob_type)
#     obj = mob_type(obj._moId)
#     obj._stub = service_instance._stub
#     return getattr(obj, attr)
