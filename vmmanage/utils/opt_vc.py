#!/usr/bin/env python
# -*- coding=utf-8 -*-
'''
@Author: ZhaoLiang
@Email: zhaoliang@hupu.com
@Date: 2020-06-08 16:10:35
@LastEditTime: 2020-06-19 17:16:48
@LastEditors: your name
@Description: 定义VC交互的操作方法
@FilePath: /Galilee/vmmanage/utils/opt_vc.py
'''

import logging
from pyVmomi import vim   #pylint: disable=no-name-in-module
from vmmanage.utils.common import LoginVC, get_vm_default_power_status, get_obj, get_storage, wait_for_task, get_random_vm_name, get_custom_spec, get_obj_prefix_label

vm_logger = logging.getLogger('optVm')

class VM():
    def __init__(self, vm_name):
        self.vm_name = vm_name
        self.vm_config = None
        self.vm_obj = get_obj([vim.VirtualMachine], self.vm_name)
        self.vm_deploy_config = None
        self.vm_device_config = None
        self.vm_custom_config = None

    def set_vm_config(self, cpus, memory_gb, annotation):
        # self.vm_name = name if name else get_random_vm_name("dev")
        self.vm_config = {
            "numCPUs": cpus,
            "numCoresPerSocket": 1,
            "memoryMB": memory_gb * 1024,
            "annotation": annotation
        }

    def set_deploy_config(self, vm_name, cluster, power_on):
        cluster = get_obj([vim.ClusterComputeResource], cluster)
        self.vm_deploy_config = {
            "name": vm_name,
            "template": self.vm_obj,
            "cluster": cluster,
            "datacenter": cluster.parent.parent,
            "power_on": power_on and power_on or get_vm_default_power_status(),
        }
        avaliable_stroage = get_storage(cluster, self.vm_device_config['disk_size'])
        vm_logger.info("当前使用存储 %s", avaliable_stroage.name)
        if avaliable_stroage:
            self.vm_deploy_config.update({"datastore": avaliable_stroage})

    def set_custom_config(self, custom_spec, ip=None, hostname=None):
        hostname = hostname if hostname else get_random_vm_name()
        self.vm_custom_config = {"hostname": hostname, "custom_spec": custom_spec, "ip": ip}

    def set_device_config(self, network=None, disk_size=None):
        vm_device_config = {}
        if network:
            vm_device_config.update({"pg_name": network})
        if disk_size:
            vm_device_config.update({"disk_size": disk_size})
        if self.vm_device_config:
            self.vm_device_config.update(vm_device_config)
        else:
            self.vm_device_config = vm_device_config

    def get_vm_obj(self):
        return self.vm_obj

    def get_power_state(self):
        return self.vm_obj.runtime.powerState


class VirtualNet():

    def __init__(self, pg_name):
        self.pg_name = pg_name
        self.dvs_obj = None
        self.pg_obj = None
        self.is_dvs = None
        self.port_obj = None

    def __isdvs(self):
        if self.is_dvs is not None:
            return self.is_dvs
        self.set_pg_obj()
        if isinstance(self.pg_obj, vim.DistributedVirtualPortgroup):
            self.is_dvs = True
            return True
        elif isinstance(self.pg_obj, vim.Network):
            self.is_dvs = False
            return False

    def set_pg_obj(self):
        self.pg_obj = get_obj([vim.Network], self.pg_name)

    def add_nic(self, vm_obj):
        '''
        @description: 用于添加网卡虚拟硬件，判断端口组是否是DVS
        @return: 返回 Spec
        '''
        nic_spec = self.__package_nic_device_spec(vm_obj)
        if self.__isdvs():
            nic_spec.device.backing = \
                vim.vm.device.VirtualEthernetCard.DistributedVirtualPortBackingInfo()
            nic_spec.device.backing.port = vim.dvs.PortConnection()
            nic_spec.device.backing.port.portgroupKey = self.port_obj.portgroupKey
            nic_spec.device.backing.port.switchUuid = self.port_obj.dvsUuid
            nic_spec.device.backing.port.portKey = self.port_obj.key
        else:
            nic_spec.device.backing = \
                vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
            nic_spec.device.backing.useAutoDetect = False
            nic_spec.device.backing.deviceName = self.port_obj
        vm_logger.info("新增虚拟机网卡Spec信息 is_dvs: %s pg_name: %s", self.is_dvs, self.pg_name)
        return nic_spec

    def edit_nic(self, vm_obj):
        nic_spec = vim.vm.device.VirtualDeviceSpec()
        nic_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
        vm_nic = None
        for dev in vm_obj.config.hardware.device:
            if isinstance(dev, vim.vm.device.VirtualEthernetCard):
                vm_nic = dev
                break
        if not vm_nic:
            vm_logger.error("VM:%s 未找到网卡信息", vm_obj.name)
            return None
        nic_spec.device = vm_nic
        if self.__isdvs():
            nic_spec.device.key = vm_nic.key
            nic_spec.device.backing = vm_nic.backing  #标准交换机和分布式交换机的backing不同
            nic_spec.device.backing.port = vim.dvs.PortConnection()
            nic_spec.device.backing.port.portgroupKey = self.port_obj.portgroupKey
            nic_spec.device.backing.port.switchUuid = self.port_obj.dvsUuid
            nic_spec.device.backing.port.portKey = self.port_obj.key
        else:
            nic_spec.device.backing = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
            nic_spec.device.backing.deviceName = self.port_obj.name
            nic_spec.device.backing.network = self.port_obj
            nic_spec.device.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
            nic_spec.device.connectable.startConnected = True
            nic_spec.device.connectable.connected = False
            nic_spec.device.connectable.allowGuestControl = True
            nic_spec.device.connectable.status = 'untried'
        vm_logger.info("编辑虚拟网卡Spec信息 vm_name: %s, is_dvs: %s, portgroup: %s", vm_obj.name, self.is_dvs, self.pg_name)
        return nic_spec

    def del_nic(self, vm_obj, obj_label):
        virtual_nic_device = None
        for device in vm_obj.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualEthernetCard) and device.deviceInfo.label == obj_label:
                virtual_nic_device = device
                break
        if not virtual_nic_device:
            vm_logger.warning("在虚拟机 %s 未找到当前虚拟设备 label: %s", vm_obj.name, obj_label)
            return None
        virtual_nic_spec = vim.vm.device.VirtualDeviceSpec()
        virtual_nic_spec.operation = \
            vim.vm.device.VirtualDeviceSpec.Operation.remove
        virtual_nic_spec.device = virtual_nic_device
        return virtual_nic_spec

    def __package_nic_device_spec(self, vm_obj):
        '''
        @description: 对网卡设备进行Spec信息封装
        @return: 返回网卡device的Spec
        '''
        nic_spec = vim.vm.device.VirtualDeviceSpec()
        nic_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add  # 用于新增
        nic_spec.device = vim.vm.device.VirtualE1000()
        nic_spec.device.deviceInfo = vim.Description()
        nic_spec.device.deviceInfo.summary = 'vCenter API test'
        # 虚拟设备接入信息
        nic_spec.device.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
        nic_spec.device.connectable.startConnected = True
        nic_spec.device.connectable.allowGuestControl = True
        nic_spec.device.connectable.connected = \
            True if vm_obj.runtime.powerState == vim.VirtualMachinePowerState.poweredOn else False
        nic_spec.device.connectable.status = 'untried'

        nic_spec.device.wakeOnLanEnabled = True
        nic_spec.device.addressType = 'assigned'  # assigned为vCenter分配mac地址
        return nic_spec

    def __find_port_by_port_key(self, port_key):
        '''
        @description: 通过port_key返回端口对象数据
        '''
        criteria = vim.dvs.PortCriteria()
        criteria.portKey = port_key
        ports = self.dvs_obj.FetchDVPorts(criteria)
        return ports

    def extend_port_for_dvs_pg(self, num):
        '''
        @description: 扩容分布式交换机的可用端口数量
        @return: task结果
        '''
        portgroup_spec = vim.dvs.DistributedVirtualPortgroup.ConfigSpec()
        portgroup_spec.configVersion = self.pg_obj.config.configVersion
        portgroup_spec.numPorts = self.pg_obj.config.numPorts + num
        task = self.pg_obj.ReconfigureDVPortgroup_Task(portgroup_spec)
        vm_logger.info("DVS的PG中没有可用端口，现动态增加端口 PG_Name:%s, 新增数量%s", self.pg_name, num)
        task_result, task_msg = wait_for_task(task, "Config Dynamic DVS Port Number")
        return task_result

    def get_available_port_by_portgroup_key(self, portgroup_key):
        '''
        @description: 通过portgroup_key过滤当前端口组中的可用端口,返回可用的port
        @return: port
        '''
        criteria = vim.dvs.PortCriteria()
        criteria.connected = False
        criteria.inside = True
        criteria.portgroupKey = portgroup_key
        ports = self.dvs_obj.FetchDVPorts(criteria)
        if len(ports) == 0:
            return False
        return ports[0]

    def search_available_port_to_dvs(self):
        '''
        @description: 通过分布式交换机获取可用的端口
        @return: 返回分布式交换机的网络接口
        '''
        available_port = self.get_available_port_by_portgroup_key(self.pg_obj.key)
        if not available_port:
            # 当没有可用的端口时，对DVS进行动态扩容端口，扩8个端口
            res = extend_port_for_dvs_pg(8)
            # 再一次获取可用端口
            available_port = res and self.get_available_port_by_portgroup_key(self.pg_obj.key) or None
        # port = available_port_key and self.find_port_by_port_key(available_port_key) or None
        return available_port

    def get_port_to_portgroup(self):
        '''
        @description: 如果是分布式交换机，1.获取分布式交换机端口组对象 2.通过端口组对象中的key值过滤当前端口组有可用端口
        @return: 返回一个可用的网络接口
        '''
        if self.__isdvs():
            self.dvs_obj = self.pg_obj.config.distributedVirtualSwitch
            self.port_obj = self.search_available_port_to_dvs()
        else:
            self.port_obj = self.pg_obj
        return self.port_obj


class VirtualDisk():

    def __init__(self, disk_size):
        self.disk_size = disk_size

    def get_disk_spec(self, vm_obj):
        '''
        @description: 封装磁盘的spec
        @return: disk_spec
        '''
        unit_number = 0
        for dev in vm_obj.config.hardware.device:
            if hasattr(dev.backing, 'fileName'):
                unit_number = int(dev.unitNumber) + 1
                # unit_number 7 reserved for scsi controller
                if unit_number == 7:
                    unit_number += 1
                if unit_number >= 16:
                    vm_logger.info("不支持多个磁盘 vm:%s", vm_obj.name)
                    return
            if isinstance(dev, vim.vm.device.VirtualSCSIController):
                controller = dev
        # add disk here
        new_disk_kb = int(self.disk_size) * 1024 * 1024
        disk_spec = vim.vm.device.VirtualDeviceSpec()
        disk_spec.fileOperation = "create"
        disk_spec.operation = "add"
        disk_spec.device = vim.vm.device.VirtualDisk()
        disk_spec.device.backing = vim.vm.device.VirtualDisk.FlatVer2BackingInfo()
        disk_spec.device.backing.thinProvisioned = True
        disk_spec.device.backing.diskMode = 'persistent'
        disk_spec.device.unitNumber = unit_number
        disk_spec.device.capacityInKB = new_disk_kb
        disk_spec.device.controllerKey = controller.key
        # print dev_changes
        vm_logger.info("虚拟机:%s 添加虚拟磁盘 %s", vm_obj.name, self.disk_size)
        return disk_spec

    def del_disk(self, vm_obj, obj_label):
        virtual_hdd_device = None
        for dev in vm_obj.config.hardware.device:
            if isinstance(dev, vim.vm.device.VirtualDisk) \
                and dev.deviceInfo.label == obj_label:
                virtual_hdd_device = dev
        if not virtual_hdd_device:
            vm_logger.warning("在虚拟机 %s 未找到当前虚拟设备 label: %s", vm_obj.name, obj_label)
            return None
        virtual_hdd_spec = vim.vm.device.VirtualDeviceSpec()
        virtual_hdd_spec.fileOperation = "destroy"
        virtual_hdd_spec.operation = "remove"
        virtual_hdd_spec.device = virtual_hdd_device
        return virtual_hdd_spec

class VirtualDevice(VirtualNet, VirtualDisk):
    '''
    @description: 对虚拟机的虚拟设备进行数据封装
    @param {type} vm {str}, pg_name {str}, disk_size {int}
    '''
    def __init__(self, vm_obj, pg_name=None, disk_size=None):
        self.vm_obj = vm_obj
        VirtualNet.__init__(self, pg_name)
        VirtualDisk.__init__(self, disk_size)

    def net_device(self, opt_type, obj_label):
        '''
        @description: 获取网卡的 Spec
        @return:  返回网卡的 Spec
        '''
        if opt_type == 'del':
            return self.del_nic(self.vm_obj, obj_label=obj_label)
        port = self.get_port_to_portgroup()  # 方法中会设置self.port_obj变量
        vm_logger.info("操作虚拟机网卡 opt_type: %s", opt_type)
        if opt_type == 'edit':
            return self.edit_nic(self.vm_obj)
        if opt_type == 'add':
            return self.add_nic(self.vm_obj)

    def disk_device(self, opt_type, obj_label):
        '''
        @description:  获取磁盘的 sepc
        @return: 返回磁盘的 Spec
        '''
        vm_logger.info("操作虚拟机磁盘 opt_type:%s", opt_type)
        if opt_type == 'del':
            return self.del_disk(self.vm_obj, obj_label=obj_label)
        if opt_type in ['add', 'edit']:
            return self.get_disk_spec(self.vm_obj)

    def get_device_config_spec(self, opt_type, obj_label=None):
        '''
        @description: 封装虚拟设备配置spec
        @return: device_config
        '''
        device_config = []
        if self.pg_name:
            nic_change = self.net_device(opt_type, obj_label)
            device_config.append(nic_change)
        if self.disk_size:
            disk_change = self.disk_device(opt_type, obj_label)
            device_config.append(disk_change)
        return device_config

class OptVM(VM):
    '''
    @description: 对虚拟机操作，包含虚拟机开机，关机，部署，修改网卡，修改磁盘，检查虚拟机状态
    '''
    def __init__(self, vm):
        VM.__init__(self, vm)

    def __package_vm_config_spec(self, device_config, opt_type, vm_config=None, obj_label=None):
        '''
        @description: 将虚拟机的设备配置信息封装到vim.vm.ConfigSpec中
        @return: 返回vim.vm.ConfigSpec
        '''
        v_device = VirtualDevice(vm_obj=self.vm_obj, **device_config)
        if vm_config:
            vm_config.update({"deviceChange": v_device.get_device_config_spec(opt_type=opt_type)})
        else:
            vm_config = {"deviceChange": v_device.get_device_config_spec(opt_type=opt_type, obj_label=obj_label)}
        for item in vm_config['deviceChange']:
            if item is None:
                vm_config['deviceChange'].remove(item)
        vmconf = vim.vm.ConfigSpec(**vm_config)
        return vmconf

    def deploy_vm(self, cpus, memory_gb, annotation, network, disk_size, vm_name, cluster, custom_spec, power_on=None, ip=None, hostname=None):
        vm_logger.info("部署虚拟机 vm_name: %s, cpus: %s, memory_gb: %s, network: %s, cluster_name: %s", vm_name, cpus, memory_gb, network, cluster)
        if get_obj([vim.VirtualMachine], vm_name):
            return False, "The name '{}' already exists.".format(vm_name)
        self.set_vm_config(cpus, memory_gb, annotation)
        self.set_device_config(network=network, disk_size=disk_size)
        vm_config_spec = self.__package_vm_config_spec(self.vm_device_config, opt_type='edit', vm_config=self.vm_config)
        print(vm_config_spec)
        self.set_deploy_config(vm_name, cluster, power_on)
        self.set_custom_config(custom_spec, ip, hostname)
        custom_spec = get_custom_spec(**self.vm_custom_config)
        self.vm_deploy_config.update({"vm_conf_spec": vm_config_spec, "custom_spec": custom_spec})
        task = self.clone_vm(**self.vm_deploy_config)
        task_result, task_msg = wait_for_task(task, "Deploy_VM")
        return task_result, task_msg

    def powerchange_vm(self, status):
        '''
        @description: 操作虚拟机开机关机
        @param {type} status {str} [ON, OFF]
        @return: task_re {bool}, task_msg {str}
        '''
        if status not in ["ON", "OFF"]:
            vm_logger.warning("未知的电源操作")
            return False, "未知的电源操作"
        current_status = self.get_power_state()
        vm_logger.info("虚拟机 VM:%s 电源状态 Status:%s，执行电源 %s", self.vm_name, current_status, status)
        if status == 'ON':
            if current_status == vim.VirtualMachinePowerState.poweredOn:
                return False, "当前虚拟机电源为打开状态"
            task = self.vm_obj.PowerOnVM_Task()
            task_res, task_msg = wait_for_task(task, "Power_On")
        elif status == "OFF":
            if current_status == vim.VirtualMachinePowerState.poweredOff:
                return False, "当前虚拟机电源为关闭状态"
            task = self.vm_obj.PowerOffVM_Task()
            task_res, task_msg = wait_for_task(task, "Power_Off")
        return task_res, task_msg

    def reset_vm(self):
        current_status = self.get_power_state()
        vm_logger.info("虚拟机 VM:%s 电源状态 Status:%s 执行重置", self.vm_name, current_status)
        task = self.vm_obj.ResetVM_Task()
        task_res, task_msg = wait_for_task(task, "Reset_VM")
        return task_res, task_msg

    def add_virtual_device(self, pg_name=None, disk_size=None):
        '''
        @description: 增加网卡或者磁盘虚拟设备
        @param {type}: pg_name {str}, disk_size {int}
        @return: 任务结果
        '''
        if pg_name:
            task_desc = "Add_Nic"
        if disk_size:
            task_desc = "Add_Disk"
        vm_device_config = {"disk_size": disk_size, "pg_name": pg_name}
        vm_config_spec = self.__package_vm_config_spec(vm_device_config, opt_type='add')
        task = self.vm_obj.ReconfigVM_Task(spec=vm_config_spec)
        task_res, task_msg = wait_for_task(task, task_desc)
        return task_res, task_msg

    def del_virtual_device(self, opt_obj, obj_number):
        '''
        @description: 根据操作的对象进行删除虚拟设备
        @param {type}: opt_obj {str} ['nic', 'disk'], obj_number {int} 这里是设备序号，例如：硬盘 1，网络适配器 2
        @return: 任务结果
        '''
        if opt_obj == 'nic':
            task_desc = "Del_Nic"
            vm_device_config = {"pg_name": True}
        if opt_obj == 'disk':
            task_desc = "Del_Disk"
            vm_device_config = {"disk_size": True}
        obj_label = get_obj_prefix_label(language="English", obj=opt_obj) + str(obj_number)
        vm_config_spec = self.__package_vm_config_spec(vm_device_config, opt_type='del', obj_label=obj_label)
        task = self.vm_obj.ReconfigVM_Task(spec=vm_config_spec)
        task_res, task_msg = wait_for_task(task, task_desc)
        return task_res, task_msg

    def clone_vm(self, name, template, custom_spec, datacenter, cluster, datastore, vm_conf_spec, power_on):
        destfolder = datacenter.vmFolder
        relospec = vim.vm.RelocateSpec()
        relospec.datastore = datastore
        relospec.pool = cluster.resourcePool
        clone_spec = vim.vm.CloneSpec()
        clone_spec.location = relospec
        clone_spec.customization = custom_spec
        clone_spec.powerOn = power_on
        clone_spec.config = vm_conf_spec
        task = template.CloneVM_Task(folder=destfolder, name=name, spec=clone_spec)
        return task

    def del_vm(self):
        task = self.vm_obj.Destroy_Task()
        task_res, task_msg = wait_for_task(task, "Destory_VM")
        return task_res, task_msg