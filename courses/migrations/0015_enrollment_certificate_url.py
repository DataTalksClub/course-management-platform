# Generated by Django 4.2.14 on 2024-08-28 12:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0014_alter_projectsubmission_github_link_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='enrollment',
            name='certificate_url',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
