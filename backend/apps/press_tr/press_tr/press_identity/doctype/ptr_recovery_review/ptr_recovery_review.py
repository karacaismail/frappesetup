from frappe.model.document import Document

from press_tr.press_identity.recovery import check_decision


class PTRRecoveryReview(Document):
	def validate(self):
		check_decision(self)
