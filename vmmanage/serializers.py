from rest_framework import serializers
from vmmanage.models import Vminfo

class VminfoSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Vminfo
        fields = ['url', 'vmname', 'cpus', 'memorys', 'instanceUuid', 'disk', 'cn', 'os', 'hostname', 'ip', 'dead_time']
