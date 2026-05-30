from django.contrib import admin
from .models import Course, Enrollment, CourseMaterial, MaterialChunk, CourseRating

admin.site.register(Course)
admin.site.register(Enrollment)
admin.site.register(CourseMaterial)
admin.site.register(MaterialChunk)
admin.site.register(CourseRating)


