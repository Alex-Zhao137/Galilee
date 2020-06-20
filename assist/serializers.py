from rest_framework import serializers
from assist.models import Job

class JobSerializer(serializers.HyperlinkedModelSerializer):
    class Meta():
        model = Job
        fields = ['url']
