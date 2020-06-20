from django.db import models

class Job(models.Model):
    job_name = models.CharField(max_length=50)
    job_id = models.PositiveSmallIntegerField()
   
