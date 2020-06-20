"""
操作AD域
"""
import json
import logging
from ldap3 import ALL, MODIFY_REPLACE, ALL_ATTRIBUTES
from ldap3 import Server, Connection, NTLM
from ldap3.core import exceptions
# from django.

# 注意：ldap3库如果要使用tls（安全连接），需要ad服务先安装并配置好证书服务，才能通过tls连接，否则连接测试时会报LDAPSocketOpenError('unable to open socket'
# 如果是进行账号密码修改及账户激活时，会报错：“WILL_NOT_PERFORM”

ldap_logger = logging.getLogger('optLdap')

# 定义一个Server
server1 = Server("127.0.0.1", port=636, use_ssl=True, get_info=ALL, connect_timeout=5)  # 设置多个AD服务器地址
server2 = Server("127.0.0.1", port=636, use_ssl=True, get_info=ALL, connect_timeout=5)
server3 = Server("127.0.0.1", port=636, use_ssl=True, get_info=ALL, connect_timeout=5)
AD_SERVER_POOL = [server1, server2, server3] 
SERVER_USER = '\\sAMAccountName@domain.com' # 域操作账号,格式为 \\sAMAccountName@domain.com
SERVER_PASSWORD = 'xxxxxxx' # 域账号密码

class OptLdap():
    """ AD中的用户与组织单位操作 """
    def __init__(self):
        """ 连接初始化 """
        self.connect = Connection( # 配置服务器连接参数
            server=AD_SERVER_POOL,
            auto_bind=True,
            authentication=NTLM, # 连接Windows AD 使用NTLM方式认证
            user=SERVER_USER,
            password=SERVER_PASSWORD,
        )
        ldap_logger.info("连接AD域服务器 %s", self.connect)
        self.leaved_base_dn = 'OU=LEAVED,DC=sh,DC=hupu,DC=com' # 离职账户的OU
        self.active_base_dn = 'OU=HUPU,DC=sh,DC=hupu,DC=com' # 在职账户的OU
        self.all_base_dn = 'DC=sh,DC=hupu,DC=com' # 所有用户的OU
        self.user_search_filter = '(objectclass=user)' # 只获取用户对象
        self.ou_search_filter = '(objectclass=organizationalUnit)' # 只获取OU对象
        self.attributes_ou = ['Name', 'ObjectGUID']
        self.attributes_user = ['name', 'memberOf', 'sAMAccountName', 'badPwdCount', 'displayName', 'mail', 'userAccountControl', 'userPrincipalName', 'telephoneNumber']

    def get_users(self, get_type='active'):
        """ 获取用户信息 """
        if get_type == 'all':
            self.connect.search(search_base=self.all_base_dn, search_filter=self.user_search_filter, attributes=self.attributes_user)
        elif get_type == 'leaved':
            self.connect.search(search_base=self.leaved_base_dn, search_filter=self.user_search_filter, attributes=self.attributes_user)
        else:
            self.connect.search(search_base=self.active_base_dn, search_filter=self.user_search_filter, attributes=self.attributes_user)
        res = json.loads(self.connect.response_to_json())['entries']
        ldap_logger.info("获取所有用户信息 %s - %s", get_type, self.connect.result)
        return res

    def get_obj_info(self, filter_key=None, filter_value=None, filter_all=None, attr=None):
        """ 根据自定义filter获取用户信息 """
        if filter_all:
            search_filter = filter_all
        else:
            search_filter = "(" + filter_key + "=" + filter_value + ")"
        res = []
        attr = attr if attr else ALL_ATTRIBUTES
        try:
            self.connect.search(search_base=self.all_base_dn, search_filter=search_filter, attributes=attr)
            res = json.loads(self.connect.response_to_json())['entries']
        except exceptions.LDAPException as ept:
            ldap_logger.error("获取自定义用户信息失败 %s", ept)
            raise
        # finally:
        #     self.connect.unbind()
        ldap_logger.info("获取自定义用户信息 %s - %s", search_filter, self.connect.result)
        return res

    def get_ous(self):
        """ 获取OU信息 """
        self.connect.search(search_base=self.active_base_dn, search_filter=self.ou_search_filter, attributes=self.attributes_ou)
        res = json.loads(self.connect.response_to_json())['entries']
        ldap_logger.info("获取所有OU信息 %s - %s", self.active_base_dn, self.connect.result)
        return res

    def del_obj(self, dn): # pylint: disable=invalid-name
        """
        删除用户 or 部门
        :param dn: 'CN=张三,OU=IT组,OU=企业信息化部,OU=虎扑,DC=sh,DC=hupu,DC=com' or 'OU=IT组,OU=企业信息化部,OU=虎扑,DC=sh,DC=hupu,DC=com'
        :return True/False
        """
        res = self.connect.delete(dn=dn)
        ldap_logger.info("用户信息 %s - %s", dn, res)
        return res, self.connect.result

    def create_obj(self, dn, obj_type, pwd="Abcd.1234", attr=None):  # pylint: disable=invalid-name
        """
        新增用户 or OU
        :param DN:  ou - "OU=IT组,OU=企业信息化部,OU=虎扑,DC=sh,DC=hupu,DC=com" or user - "CN=张三,OU=IT组,OU=企业信息化部,OU=虎扑,DC=sh,DC=hupu,DC=com"
        :param obj_type: user or ou
        :param attr: user - {"sAMAccountName": "zhangsan",
                            "Sn": "张",
                            "name":"张三",
                            "UserPrincipalName": "zhangsan@sh.hupu.com",
                            "Mail": "zhangsan@hupu.com",
                            "Displayname": "张三"}
                    ou - {"name": "IT组"}
        :return : {"status": True/False, "msg": {}}
        """
        res = False
        ldap_logger.info("创建AD域Object %s - %s_attr:%s", dn, obj_type, attr)
        object_class = {'user': ['top', 'person', 'organizationalPerson', 'user'], 'ou': ['top', 'organizationalUnit']}
        try:
            res = self.connect.add(dn=dn, object_class=object_class[obj_type], attributes=attr)
            ldap_logger.info("创建Object结果 %s - %s - %s", dn, self.connect.result, res)
            msg = self.connect.result
            if obj_type == 'user': # 如果是用户，需要设置密码、激活账号
                self.connect.extend.microsoft.modify_password(dn, pwd)  # 设置密码
                self.connect.modify(dn, {'userAccountControl': [(MODIFY_REPLACE, 512)]})  # 设置账号状态，激活用户
        except exceptions.LDAPException as ept:
            ldap_logger.error("Object信息 %s - %s - %s", dn, self.connect, ept)
            msg = "Ldap新增Object操作失败，详细信息查看Log"
        # finally:
        #     self.connect.unbind()
        return res, msg

    def update_obj(self, dn, attr=None):  # pylint: disable=invalid-name
        """
        更新user or OU
        只允许OU更新name，user不能更新 ["name","sAMAccountName", "userPrincipalName", "displayname"]
        OU or USER都可以移动
        :param dn: 需要修改的完整DN
        :param attr: 需要更新的属性值，字典形式
        :return {"status: True/False, "msg": {'result': 0, 'description': 'success', 'dn': '', 'message': '', 'referrals': None, 'type': 'modDNResponse'}}
        """
        changes_dic = {}
        ldap_logger.info("更新Object的信息 %s - %s", dn, attr)
        for k, v in attr.items():  # pylint: disable=invalid-name
            if not self.compare_attr(dn=dn, attr=k, value=v):
                ldap_logger.info("对比Object信息结果 %s - %s:%s - %s", dn, k, v, self.connect.result)
                if k == "name":   # 修改name值只允许OU修改，不允许修改CN的name
                    res = self._rename_obj(dn=dn, newname=attr['name'])
                    if res['description'] == 'success':
                        if dn[:2] == "OU":
                            dn = "OU=%s,%s" % (attr["name"], dn.split(",", 1)[1])
                        else:
                            return {"status": False, "msg": "不支持的DN " + dn}
                elif k == "DistinguishedName":
                    res = self._move_object(dn=dn, new_dn=v) # 调用移动User or OU 的方法
                    if res['description'] == 'success':
                        if dn[:2] == "CN":
                            dn = "%s" % (attr["DistinguishedName"])
                        if dn[:2] == "OU":
                            dn = "%s" % (attr["DistinguishedName"])
                elif k in ["sAMAccountName", "userPrincipalName", "displayname"]:
                    return {"status": False, "msg": "不支持的属性 " + k}
                else:
                    changes_dic.update({k:[(MODIFY_REPLACE, [v])]})
                    self.connect.modify(dn=dn, changes=changes_dic)
        return {"status": True, "msg": self.connect.result}

    def _rename_obj(self, dn, newname):  # pylint: disable=invalid-name
        """
        OU or User 重命名方法
        :param dn:需要修改的object的完整dn路径
        :param newname: 新的名字
        :return:返回中有：'description': 'success', 表示操作成功
        {'result': 0, 'description': 'success', 'dn': '', 'message': '', 'referrals': None, 'type': 'modDNResponse'}
        """
        cn_ou = dn.split("=", 1)
        newname = cn_ou[0] + "=" + newname
        res = self.connect.modify_dn(dn, newname)
        ldap_logger.info("Remove-Object-Info %s - %s - %s", dn, self.connect.result, res)
        return self.connect.result


    def _move_object(self, dn, new_dn):  # pylint: disable=invalid-name
        """移动员工 or 部门到新部门"""
        relative_dn, superou = new_dn.split(",", 1)
        res = self.connect.modify_dn(dn=dn, relative_dn=relative_dn, new_superior=superou)
        ldap_logger.info("Move-Object-Info %s - %s - %s", dn, self.connect.result, res)
        return self.connect.result

    def leaved_user(self, dn):   # pylint: disable=invalid-name
        """ 处理离职的用户，离职用户放置在离职OU里，账号禁用 """
        res = self.connect.modify(dn, {'userAccountControl': [(MODIFY_REPLACE, 514)]})  # 设置账号状态，禁用账号
        ldap_logger.info("Leaved-User %s - Disable - %s", dn, res)
        if res:
            new_dn = dn.split(",")[0] + "," + self.leaved_base_dn
            res = self._move_object(dn=dn, new_dn=new_dn)
        return res

    def compare_attr(self, dn, attr, value):   # pylint: disable=invalid-name
        """比较员工指定的某个属性
        """
        try:
            res = self.connect.compare(dn=dn, attribute=attr, value=value)
            ldap_logger.info("Commpare-Object-Info %s - %s:%s - %s", dn, attr, value, res)
        except exceptions.LDAPException as ept:
            ldap_logger.error("Commpare-Object-Info-Expception %s - %s - %s", dn, self.connect, ept)
            res = False
        return res

    def reset_password(self, dn, new_pwd):  # pylint: disable=invalid-name
        """ 重置密码， 不需要原密码 """
        res = self.connect.extend.microsoft.modify_password(dn, new_pwd)
        ldap_logger.info("Reset-Password %s - %s", dn, self.connect.result)
        return res, self.connect.result


def check_credentials(username, password):
    """ 用户认证测试接口 """
    res = {}
    ldap_user = '\\{}@sh.hupu.com'.format(username)
    try:
        connect = Connection(server1, user=ldap_user, password=password, authentication=NTLM)
        res = {'status': connect.bind(), 'msg': str(connect.result)}
        ldap_logger.info("用户 %s 登录验证成功 %s", username, str(connect.result))
    except exceptions.LDAPException as ept:
        ldap_logger.warning("用户 %s 登录验证出现错误 %s", username, ept)
        res = {'status': False, 'msg': ept}
    finally:
        connect.unbind()
    return res
