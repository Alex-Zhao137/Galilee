from rest_framework import serializers
from django.contrib.auth.models import User, Group
from infox.models import  Orginfo, Userinfo


class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta():
        model = User
        fields = ['url', 'username', 'email', 'groups', 'last_login']

class GroupSerializer(serializers.HyperlinkedModelSerializer):
    class Meta():
        model = Group
        fields = ['url', 'name']

class UserinfoSerializer(serializers.HyperlinkedModelSerializer):
    status = serializers.CharField(source='get_userAccountControl_display', default='a')
    org = serializers.CharField(source='org.objectGUID')
    class Meta:
        model = Userinfo
        fields = ['url', 'id', 'displayName', 'name', 'dn', 'sAMAccountName', 'userPrincipalName', 'badPwdCount', 'memberOf', 'mail', 'telephoneNumber', 'status', 'userAccountControl', 'org']

    def create(self, validated_data):
        validated_data.pop('get_userAccountControl_display')
        validated_data['org'] = Orginfo.objects.get(pk=validated_data['org']['objectGUID'])
        return Userinfo.objects.create(**validated_data)

    def update(self, instance, validated_data):
        instance.mail = validated_data.get('mail', instance.mail)
        instance.telephoneNumber = validated_data.get('telephoneNumber', instance.telephoneNumber)
        if 'dn' in validated_data:
            instance.dn = validated_data.get('dn', instance.dn)
            instance.org = Orginfo.objects.get(dn=instance.dn.split(",", 1)[1])
        instance.save()
        return instance


class OrginfoSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Orginfo
        fields = ['url', 'dn', 'name', 'objectGUID']
