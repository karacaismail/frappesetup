from education.education.doctype.student.student import Student


class CustomStudent(Student):
	def validate(self):
		self.title = self.first_name
