"""
创建视图
"""
import logging
import uuid
from rest_framework import viewsets
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.settings import api_settings
from rest_framework.response import Response
from rest_framework.decorators import action
from django.contrib.auth.models import User, Group
from infox.models import Orginfo, Userinfo
from infox.serializers import UserSerializer, GroupSerializer, OrginfoSerializer, UserinfoSerializer

from infox.utils.opt_ldap import OptLdap
from infox.utils.opt_ldap import check_credentials

views_logger = logging.getLogger("infox")

class UserViewSet(viewsets.ModelViewSet):
    """ 用户视图集合 """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

class GroupViewSet(viewsets.ModelViewSet):
    """ 用户组视图集合 """
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    permission_classes = [permissions.IsAuthenticated]

class UserinfoViewSet(viewsets.ModelViewSet):
    """ AD域用户信息视图集合 """
    queryset = Userinfo.objects.all().order_by("id")
    serializer_class = UserinfoSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(methods=['post'], detail=False, permission_classes=[permissions.IsAuthenticated])
    def sync_user(self, request, *args, **kwargs):     
        """ 将AD域用户信息同步到系统 """
        args = request.data
        args['org'] = Orginfo.objects.get(dn=args['org'])
        views_logger.info(args)
        query, status = Userinfo.objects.get_or_create(sAMAccountName=args['sAMAccountName'], defaults=args)
        views_logger.info("系统同步到域信息 name:%s - %s", query.name, status)
        ser = self.get_serializer(query)
        return Response(ser.data)

    @action(methods=['post'], detail=True, permission_classes=[permissions.IsAuthenticated])
    def update_user(self, request, *args, **kwargs):    
        """
        从钉钉更新用户
        :URL: /userinfo/<pk>/
        :PK - sAMAccountName
        :param {"mail": "zhangsan@hupu.com", "telephoneNumber": "11122233345", "deptId": 11}
        """
        if 'pk' not in kwargs:
            return Response({'status': False, 'msg': "无用户名信息！"})
        data = request.data
        query = Userinfo.objects.get(sAMAccountName=kwargs['pk'])
        for i in data:
            if i not in ['mail', 'telephoneNumber', 'deptId']:
                return Response({"status": False, "msg": "参数中包含不可更新的内容 key:" + i + " - value:" + data[i]})
        org_uuid = data.pop('deptId')
        if org_uuid != query.org.objectGUID:
            org_query = Orginfo.objects.get(objectGUID=org_uuid)
            data['DistinguishedName'] = "CN=%s,%s" % (query.displayName, org_query.dn)
        opt_ldap = OptLdap()
        res = opt_ldap.update_obj(query.dn, data)
        if not res['status']:
            return Response(res)
        if 'DistinguishedName' in data:
            data.update({'dn': data.pop("DistinguishedName")})
        self.kwargs.update({'partial': True, 'pk': query.id})
        request._full_data = data    # pylint: disable=protected-access
        res = self.update(request, **self.kwargs)   # pylint: disable=no-member
        if res.status_code != 200:
            views_logger.warning("数据库更新操作失败 ID:%s - %s - %s", query.id, data, "False")
            return Response({"status": False, "msg": "AD域更新成功，数据库更新失败，详细信息请查看系统Log"})
        views_logger.info("数据库更新操作成功 ID:%s - %s - %s", query.id, data, "True")
        return Response({"status": True, "msg": "success", "obj": res.data})

    def partial_update(self, request, *args, **kwargs):   
        """
        从钉钉更新用户
        :param
        """
        return Response({'status': False, 'msg': "不支持PATCH方式提交"})

    def create(self, request, *args, **kwargs):
        """
        从钉钉新增域用户
        : param  {"name": "张三", "sAMAccountName": "zhangsan", "mail": "zhangsan@hupu.com", "telephoneNumber": "11122233345", "pwd": "123456", "deptId": 11}
        """
        new_data = {}
        data = request.data
        org_query = Orginfo.objects.get(objectGUID=data['deptId'])   # 获取部门信息
        new_data = {k:v for k, v in data.items() if k not in ['pwd', 'deptId']}
        new_data.update({'displayName': data['name'], 'userPrincipalName': data['sAMAccountName'] + "@sh.hupu.com"})
        dn = "CN=%s,%s" % (data['name'], org_query.dn)     # 构造dn   pylint: disable=invalid-name
        opt_ldap = OptLdap()
        check = opt_ldap.get_obj_info(filter_key="sAMAccountName", filter_value=data['sAMAccountName'], attr=['name', 'Displayname'])   # 查询AD域中是否有该账号
        if len(check) != 0:
            return Response({"status": False, "msg": "AD域中存在该用户 " + data['sAMAccountName']})
        res, msg = opt_ldap.create_obj(dn, 'user', data['pwd'], new_data)
        if not res:
            views_logger.warning("AD域创建用户失败 %s - %s - %s", dn, new_data, "False")
            return Response({"status": res, "msg": "AD域创建用户失败 " + str(msg)})
        views_logger.warning("AD域创建用户成功 %s - %s - %s", dn, new_data, "True")
        new_data.update({'dn': dn, 'userAccountControl': 512, 'org': org_query.id})
        request._full_data = new_data             # 修改request.data的值   pylint: disable=protected-access  
        res = super().create(request)
        if res.status_code != 201:
            views_logger.warning("数据库新增操作失败 %s - %s - %s", dn, new_data, "False")
            return Response({"status": False, "msg": "AD域成功创建，数据库创建失败，详细信息请查看系统Log"})
        views_logger.info("数据库新增操作 %s - %s", new_data, "True")
        return Response({"status": True, "msg": "success", "obj": res.data})

    @action(methods=['get'], detail=True, permission_classes=[permissions.IsAuthenticated])
    def leave_user(self, request, *args, **kwargs):    
        """
        用户离职
        :param   /userinfo/<pk>
        pk = sAMAccountName
        """
        if 'pk' not in kwargs:
            return Response({'status': False, 'msg': "无用户名信息！"})
        query = Userinfo.objects.get(sAMAccountName=kwargs['pk'])
        opt_ldap = OptLdap()
        res = opt_ldap.leaved_user(query.dn)
        if not res:
            views_logger.warning("AD域操作用户离职失败 DN:%s - %s", query.dn, "False")
            return Response({"status": False, "msg": "AD域操作失败，详细信息请查看LDAP Log。"})
        views_logger.warning("AD域操作用户离职 DN:%s - %s", query.dn, "True")
        self.kwargs['pk'] = query.id
        res = self.destroy(self, request)  #pylint: disable=no-member
        if res.status_code != 204:
            views_logger.warning("数据库操作失败 ID:%s - %s - %s", query.id, query.dn, "False")
            return Response({"status": False, "msg": "AD域操作成功，数据库操作失败，详细信息请查看系统Log。"})
        views_logger.info("数据库删除操作 ID：%s - %s - %s", query.id, query.dn, "True")
        return Response({"status": True, "msg": "success"})

    @action(methods=['post'], detail=False, permission_classes=[permissions.IsAuthenticated])
    def reset_password(self, request, *args, **kwargs):    
        """ 重置AD域密码 """
        args = request.data
        if 'name' not in args or 'pwd' not in args:
            return Response({'status': False, 'msg': "提交的用户名和密码信息有误！"})
        query = Userinfo.objects.get(sAMAccountName=args['name'])
        opt_ldap = OptLdap()
        res, msg = opt_ldap.reset_password(query.dn, args['pwd'])
        views_logger.info("AD域重置密码 sAMAccountName:%s - %s - %s", args['name'], msg, res)
        return Response({"status": res, "msg": msg['description']})

    @action(methods=['get'], detail=True, permission_classes=[permissions.IsAuthenticated])
    def del_user(self, request, *args, **kwargs):  
        """ 删除离职用户 """
        if 'pk' not in kwargs:
            return Response({'status': False, 'msg': "无用户名信息！"})
        opt_ldap = OptLdap()
        res = opt_ldap.get_obj_info(filter_key='sAMAccountName', filter_value=kwargs['pk'], attr=['name', 'displayName', 'sAMAccountName'])
        if len(res) == 0:
            views_logger.info("AD域不存在该用户 %s - %s", kwargs['pk'], "False")
            return Response({"status": False, "msg": "AD域中没有该用户，详细信息请查看Log"})
        res, msg = opt_ldap.del_obj(res[0]['dn'])
        views_logger.info("AD域删除用户 %s - %s", msg, res)
        return Response({"status": res, "msg": msg['description']})

    @action(methods=['post'], detail=False, permission_classes=[permissions.IsAuthenticated])
    def check_exist(self, request, *args, **kwargs):
        """
        检查账号是否存在
        :param {"name": "张三", "sAMAccountName": "zhangsan"}
        """
        data = request.data
        if not data:
            return Response({"status": False, "msg": "未接收到任何请求参数"})
        opt_ldap = OptLdap()
        if "operator" in data:
            filter_all = data.pop('operator')
            for i in data['obj']:
                filter_all = "{}({}={})".format(filter_all, i, data['obj'][i])
            res = opt_ldap.get_obj_info(filter_all="(" + filter_all + ")", attr=None)
        if len(data) == 1:
            res = opt_ldap.get_obj_info(filter_key=list(data.keys())[0], filter_value=list(data.values())[0], attr=None)
        if len(res) == 0:
            return Response({"status":False, "msg": "not user", "obj": res})
        return Response({"status":True, "msg": "success", "obj": res})


class OrginfoViewSet(viewsets.ModelViewSet):
    """ AD域部门(OU)信息视图集合 """
    queryset = Orginfo.objects.all().order_by('objectGUID')
    serializer_class = OrginfoSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(methods=['post'], detail=False, permission_classes=[permissions.IsAuthenticated])
    def sync_org(self, request, *args, **kwargs):
        """ 将AD域OU信息同步到系统 """
        args = request.data
        views_logger.info(args)
        query, status = Orginfo.objects.get_or_create(objectGUID=args['objectGUID'], defaults=args)
        views_logger.info("系统同步到域信息 name:%s - %s", query.name, status)
        ser = self.get_serializer(query)
        return Response(ser.data)

    def create(self, request, *args, **kwargs):
        """ 创建OU接口 """
        data = request.data
        for i in data:
            if i not in ['name', 'parent_objectGUID']:
                return Response({"status": False, "msg": "参数中包含异常的内容 key:" + i + " - value:" + data[i]})
        parent_dpt_query = Orginfo.objects.get(objectGUID=data.pop('parent_objectGUID'))
        dn = "OU=%s,%s" % (data['name'], parent_dpt_query.dn)   #pylint: disable=invalid-name
        opt_ldap = OptLdap()
        res, msg = opt_ldap.create_obj(dn=dn, obj_type="ou")
        if not res:
            views_logger.warning("AD域创建OU失败 %s - %s - %s", dn, msg, res)
            return Response({"status": False, "msg": "AD域创建OU失败 - " + str(msg)})
        ad_info = opt_ldap.get_obj_info(filter_key="DistinguishedName", filter_value=dn, attr=['objectGUID'])
        data.update({'dn': dn, 'objectGUID': str(uuid.UUID(ad_info[0]['attributes']['objectGUID']))})
        request._full_data = data             # 修改request.data的值   pylint: disable=protected-access  
        res = super().create(request)
        if res.status_code != 201:
            views_logger.warning("数据库新增操作失败 %s - %s - %s", dn, data, "False")
            return Response({"status": False, "msg": "AD域成功创建，数据库创建失败，详细信息请查看系统Log"})
        views_logger.info("数据库新增操作成功 %s - %s", data, "True")
        return Response({"status": True, "msg": "success", "obj": res.data})

    @action(methods=['get'], detail=True, permission_classes=[permissions.IsAuthenticated])
    def del_org(self, request, *args, **kwargs):
        """ 删除OU接口 """
        if "pk" not in kwargs:
            return Response({'status': False, 'msg': "无OU的UUID信息！"})
        opt_ldap = OptLdap()
        ad_info = opt_ldap.get_obj_info(filter_key='objectGUID', filter_value=kwargs['pk'], attr=opt_ldap.attributes_ou)   # 删除AD域中OU信息
        if len(ad_info) == 0:   # 检查该信息是否在AD域中存在
            views_logger.info("AD域不存在该OU %s - %s", kwargs['pk'], "False")
            return Response({"status": False, "msg": "AD域中没有该用户，详细信息请查看Log"})
        res, msg = opt_ldap.del_obj(ad_info[0]['dn'])
        if not res:
            views_logger.warning("AD域删除OU失败 %s - %s", msg, res)
            return Response({'status': False, 'msg': "无OU的UUID信息！"})
        views_logger.warning("AD域操作用户离职 DN:%s - %s", ad_info[0]['dn'], "True")
        db_info = Orginfo.objects.get(objectGUID=kwargs['pk'])
        self.kwargs['pk'] = db_info.id
        res = self.destroy(self, request)  #pylint: disable=no-member
        if res.status_code != 204:
            views_logger.warning("数据库操作失败 ID:%s - %s", ad_info[0]['dn'], "False")
            return Response({"status": False, "msg": "AD域操作成功，数据库操作失败，详细信息请查看系统Log。"})
        views_logger.info("数据库删除操作 ID：%s - %s", ad_info[0]['dn'], "True")
        return Response({"status": True, "msg": "success"})

    @action(methods=['post'], detail=True, permission_classes=[permissions.IsAuthenticated])
    def update_org(self, request, *args, **kwargs):
        """
        更新OU接口
        :URL: /orginfo/<pk>/
        :PK - objectGUID
        :param {"name": "测试", "parentID": "11122233345"}
        """
        if "pk" not in kwargs:
            return Response({'status': False, 'msg': "无OU的UUID信息！"})
        data = request.data
        attr = {}
        current_ou = Orginfo.objects.get(objectGUID=kwargs['pk'])
        if "parentID" in data:
            new_ou_path = Orginfo.objects.get(objectGUID=data['parentID'])
            attr['DistinguishedName'] = "OU={},{}".format(data['name'], new_ou_path.dn)
            if current_ou.dn == attr['DistinguishedName']:
                attr.pop("DistinguishedName")
        if "name" in data:
            if current_ou.name != data['name']:
                attr['name'] = data['name']
        views_logger.info("更新部门信息 dn:%s attr:%d", current_ou.dn, attr)
        opt_ldap = OptLdap()
        res = opt_ldap.update_obj(dn=current_ou.dn, attr=attr)
        if not res['status']:
            return Response(res)
        self.kwargs.update({'partial': True, 'pk': current_ou.id})
        request._full_data = attr    # pylint: disable=protected-access
        res = self.update(request, **self.kwargs)   # pylint: disable=no-member
        if res.status_code != 200:
            views_logger.warning("数据库更新操作失败 ID:%s - %s - %s", current_ou.id, attr, "False")
            return Response({"status": False, "msg": "AD域更新成功，数据库更新失败，详细信息请查看系统Log"})
        views_logger.info("数据库更新操作成功 ID:%s - %s - %s", current_ou.id, attr, "True")
        return Response({"status": True, "msg": "success", "obj": res.data})

    def partial_update(self, request, *args, **kwargs):
        """
        禁用PATCH方法
        :param
        """
        return Response({'status': False, 'msg': "不支持PATCH方式提交"})

class ApiInfoView(APIView):

    def get(self, request):
        available = {"description": "Galilee REST API", "available_versions": {i: "/api/" + i + "/" for i in api_settings.ALLOWED_VERSIONS}}
        return Response(available)

class CheckAuthViewSet(viewsets.GenericViewSet):
    """ 用于验证账号登录测试 """
    def create(self, request, *args, **kwargs):
        args = request.data
        if 'name' not in args or 'pwd' not in args:
            return Response({'status': False, 'msg': "提交的用户名和密码信息有误！"})
        check_res = check_credentials(args['name'], args['pwd'])
        return Response(check_res)
