"""
定义InfoX数据模型
"""
import datetime
import logging
from django.db import models

model_logger = logging.getLogger("galilee")

class UserinfoManager(models.Manager):
    def get_dn_by_account(self, account):
        try:
            res = self.get(sAMAccountName=account)
        except Userinfo.DoesNotExist as ept:
            model_logger.warning("%s - %s", account, ept)
            raise
        return res.dn

class Userinfo(models.Model):
    userStatus = [
        ('512', 'a'), # 账号正常
        ('514', 'b'), # 账号已禁用
        ('544', 'c'), # 下次登录修改密码
        ('546', 'c, b'), # 下次登录修改密码, 用户已禁用
        ('66048', 'd'), # 密码永不过期
        ('66050', 'd, b'), # 密码永不过期, 用户已禁用
        ('66080', 'd, c') # 密码永不过期, 下次登录修改密码
    ]
    name = models.CharField(max_length=50)
    displayName = models.CharField(max_length=50)
    dn = models.CharField(max_length=100, blank=True)
    memberOf = models.TextField(blank=True)
    badPwdCount = models.PositiveSmallIntegerField(blank=True, default=0)
    sAMAccountName = models.CharField(max_length=20, unique=True)
    userPrincipalName = models.CharField(max_length=40)
    mail = models.CharField(max_length=40, blank=True)
    telephoneNumber = models.CharField(max_length=12, blank=True)
    userAccountControl = models.CharField(choices=userStatus, max_length=8, blank=True)
    org = models.ForeignKey('Orginfo', models.SET_NULL, null=True, blank=True)
    objects = UserinfoManager()

    def get_status(self):
        res = []
        tmp = self.userAccountControl
        tmp = tmp - 512
        attr = {'8388608': '密码已过期',
                '65535': '密码永不过期',
                '64': '用户不可更改密码(只读)',
                '32': '下次登录修改密码',
                '16': '用户被锁定',
                '2': '用户已禁用'}
        for k, v in attr.items():   # pylint: disable=invalid-name
            if data < int(k):
                continue
            tmp = data-int(k)
            if tmp >= 0:
                res.append(v)
                data = tmp
            else:
                break
        res = ['y'] if len(res) == 0 else res
        return res


class Orginfo(models.Model):
    name = models.CharField(max_length=50)
    objectGUID = models.CharField(max_length=40, unique=True)
    dn = models.CharField(max_length=100)
