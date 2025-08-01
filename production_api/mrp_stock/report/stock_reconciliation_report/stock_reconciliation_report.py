# Copyright (c) 2025, Essdee and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data

def get_columns():
	return [
		{"fieldname": "owner", "fieldtype": "Link", "options": "User", "label": "Owner"},
		{"fieldname": "creation", "fieldtype": "Datetime", "label": "Creation"},
		{"fieldname": "modified_by", "fieldtype": "Link", "options": "User", "label": "Modified By"},
		{"fieldname": "modified", "fieldtype": "Datetime", "label": "Modified"},
		{"fieldname": "stock_reconciliation","fieldtype": "Link","label": "Stock Reconciliation",
   			"options": "Stock Reconciliation", "width": 200},
		{"fieldname": "purpose","fieldtype": "Data","label": "Purpose", "width": 130},
		{"fieldname": "posting_date", "fieldtype": "Date", "label": "Posting Date"},
		{"fieldname": "supplier","fieldtype": "Link","label": "Supplier","options": "Supplier", "width": 100},
		{"fieldname": "supplier_name","fieldtype": "Data","label": "Supplier Name", "width": 200},
		{"fieldname": "lot","fieldtype": "Link","label": "Lot","options": "Lot", "width": 100},
		{"fieldname": "item","fieldtype": "Link","label": "Item","options": "Item", "width": 250},
		{"fieldname": "item_variant","fieldtype": "Link","label": "Item Variant","options": "Item Variant", "width": 250},
		{"fieldname": "previous_quantity","fieldtype": "Float","label": "Previous Quantity", "width": 100},
		{"fieldname": "updated_quantity","fieldtype": "Float","label": "Updated Quantity", "width": 100},
		{"fieldname": "previous_queue", "fieldtype":"Data", "label":"Previous Queue"},
		{"fieldname": "updated_queue", "fieldtype":"Data", "label":"Updated Queue"},
		{"fieldname": "previous_rate", "fieldtype":"Currency", "label":"Previous Rate"},
		{"fieldname": "updated_rate", "fieldtype":"Currency", "label":"Updated Rate"},
		{"fieldname": "difference","fieldtype": "Float","label": "Difference", "width": 100},
		{"fieldname": "uom","fieldtype": "Link","label": "UOM","options": "UOM", "width": 100},
	]

def get_data(filters):
	con = {}
	con['from_date'] = filters.get("from_date")
	con['to_date'] = filters.get("to_date")
	conditions = ""

	if filters.get("supplier"):
		conditions += f" AND default_warehouse = %(supplier)s"
		con['supplier'] = filters.get("supplier")	

	sre_list = frappe.db.sql(
		f"""
			SELECT name, purpose, default_warehouse, owner, creation, modified, modified_by, posting_date 
				FROM `tabStock Reconciliation` WHERE posting_date BETWEEN %(from_date)s AND %(to_date)s
				AND docstatus = 1 {conditions}
		""", con, as_dict=True
	)
	data = []
	for sre in sre_list:
		purpose = sre['purpose']
		supplier_name = frappe.get_cached_value("Supplier", sre['default_warehouse'], "supplier_name")
		con = {}
		con['sre'] = sre['name']
		conditions = ""
		if filters.get("lot"):
			con['lot'] = filters.get("lot")
			conditions += f" AND lot = %(lot)s"

		if filters.get("item_variant"):
			con['item_variant'] = filters.get("item_variant")
			conditions += f" AND item = %(item_variant)s"	

		sre_table_items = frappe.db.sql(
			f"""
				SELECT name FROM `tabStock Reconciliation Item` WHERE parent = %(sre)s {conditions}
			""", con, as_dict=True
		)
		for tabel_item in sre_table_items:
			sle_data = frappe.db.sql(
				"""
					SELECT name, posting_datetime, item, lot, warehouse, qty_after_transaction, uom,
						valuation_rate, stock_queue FROM `tabStock Ledger Entry` WHERE 
						voucher_type = 'Stock Reconciliation' 
						AND voucher_no = %(docname)s 
						AND voucher_detail_no = %(table_row_name)s
				""", {
					"docname": sre['name'],
					"table_row_name": tabel_item['name'],
				}, as_dict=True
			)
			if not sle_data:
				continue
			previous_data = frappe.db.sql(
				"""
					SELECT name, qty_after_transaction, stock_queue, valuation_rate 
						FROM `tabStock Ledger Entry` WHERE item = %(item)s AND 
						warehouse = %(warehouse)s AND lot = %(lot)s 
						AND posting_datetime < %(datetime)s ORDER BY posting_datetime 
						DESC LIMIT 1
				""", {
					"item": sle_data[0]['item'],
					"lot": sle_data[0]['lot'],
					"warehouse": sle_data[0]['warehouse'],
					"datetime": sle_data[0]['posting_datetime']
				}, as_dict=True
			)
			previous_qty = 0
			previous_queue = None
			previous_rate = None
			if previous_data:
				previous_qty = previous_data[0]['qty_after_transaction']
				previous_queue = previous_data[0]['stock_queue']
				previous_rate = previous_data[0]['valuation_rate']

			item_name = frappe.get_cached_value("Item Variant", sle_data[0]['item'], "item")
			if filters.get('item') and item_name != filters.get("item"):
				continue

			data.append(
				{
					"owner": sre['owner'],
					"creation": sre['creation'],
					"modified_by": sre['modified_by'],
					"modified": sre['modified'],
					"posting_date": sre['posting_date'],
					"stock_reconciliation": sre['name'],
					"purpose": purpose,
					"supplier": sle_data[0]['warehouse'],
					"supplier_name": supplier_name,
					"lot": sle_data[0]['lot'],
					"item": item_name,
					"item_variant": sle_data[0]['item'],
					"previous_quantity": previous_qty,
					"updated_quantity": sle_data[0]['qty_after_transaction'],
					"previous_queue": previous_queue,
					"updated_queue": sle_data[0]['stock_queue'],
					"previous_rate": previous_rate,
					"updated_rate": sle_data[0]['valuation_rate'],
					"difference": sle_data[0]['qty_after_transaction'] - previous_qty,
					"uom": sle_data[0]['uom'],
				}
			)
	return data
