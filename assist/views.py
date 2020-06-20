#!/usr/bin/env python
# -*- coding=utf-8 -*-
'''
@Author: your name
@Email: zhaoliang@hupu.com
@Date: 2020-06-19 15:47:33
@LastEditTime: 2020-06-19 15:48:03
@LastEditors: your name
@Description: 
@FilePath: /Galilee/assist/views.py
'''
from rest_framework import viewsets
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.parsers import JSONParser
from assist.models import Job
from assist.serializers import JobSerializer

class AssistViewSet(viewsets.ModelViewSet):
    queryset = Job.objects.all()
    serializer_class = JobSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        return Response("ceshi")

    def destroy(self, request, *args, **kwargs):
        return Response("ceshi")

    def update(self, request, *args, **kwargs):
        return Response("ceshi")
