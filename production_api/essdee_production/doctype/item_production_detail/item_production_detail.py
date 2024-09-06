# Copyright (c) 2024, Essdee and contributors
# For license information, please see license.txt
import frappe, json
import math
from frappe.model.document import Document
from frappe.utils import flt, now_datetime
from six import string_types
from itertools import groupby
from production_api.production_api.doctype.item.item import get_or_create_variant
from production_api.production_api.doctype.item_dependent_attribute_mapping.item_dependent_attribute_mapping import get_dependent_attribute_details
from production_api.essdee_production.doctype.production_order.production_order import get_uom_conversion_factor
class ItemProductionDetail(Document):
	def load_attribute_list(self):
		attribute_list = []
		for attribute in self.item_attributes:
			attribute_doc = frappe.get_doc("Item Attribute", attribute.attribute)
			if not attribute_doc.numeric_values:
				if attribute.mapping != None:
					doc = frappe.get_doc("Item Item Attribute Mapping", attribute.mapping)
					attribute_list.append({
						'name': attribute.name,
						'attr_name': attribute.attribute,
						'attr_values_link': attribute.mapping,
						'attr_values': doc.values,
						'doctype': 'Item Item Attribute Mapping'
					})
				else:
					attribute_list.append({
						'name': attribute.name,
						'attr_name': attribute.attribute,
						'attr_values_link': attribute.mapping,
						'attr_values': [],
						'doctype': 'Item Item Attribute Mapping'
					})
		self.set_onload('attr_list', attribute_list)

	def load_bom_attribute_list(self):
		bom_attribute_list = []
		for bom in self.item_bom:
			if bom.attribute_mapping != None:
				doc = frappe.get_doc("Item BOM Attribute Mapping", bom.attribute_mapping)
				bom_attribute_list.append({
					'bom_item': bom.item,
					'bom_attr_mapping_link': bom.attribute_mapping,
					'bom_attr_mapping_based_on': bom.based_on_attribute_mapping,
					'bom_attr_mapping_list': doc.values,
					'doctype': 'Item BOM Attribute Mapping'
				})
		self.set_onload('bom_attr_list', bom_attribute_list)

	def load_dependent_attribute(self):
		"""Load Dependent Attribute Detail into `__onload`"""
		dependent_attribute = {}
		if self.dependent_attribute and self.dependent_attribute_mapping:
			dependent_attribute = get_dependent_attribute_details(self.dependent_attribute_mapping)
			
		self.set_onload('dependent_attribute', dependent_attribute)	

	def onload(self):
		self.load_attribute_list()
		self.load_bom_attribute_list()
		self.load_dependent_attribute()
		set_items = fetch_set_items(self.get('set_item_combination_details'))
		if len(set_items['values']) > 0:
			self.set_onload('set_item_detail',set_items)

	def before_validate(self):
		if self.get('set_item_detail'):
			set_details = save_item_details(self.set_item_detail)
			self.set('set_item_combination_details', set_details)
		if not self.is_set_item:
			self.set('set_item_combination_details', [])
			self.set('major_attribute_value', None)
			self.set('set_item_attribute', None)

	def validate(self):
		if self.get('__islocal'):
			for attribute in self.get('item_attributes'):
				if attribute.mapping:
					doc = frappe.get_doc("Item Item Attribute Mapping", attribute.mapping)
					duplicate_doc = frappe.new_doc("Item Item Attribute Mapping")
					duplicate_doc.attribute_name = doc.attribute_name
					duplicate_doc.values = doc.values
					duplicate_doc.save()
					attribute.mapping = duplicate_doc.name

			if self.dependent_attribute_mapping:
				doc = frappe.get_doc('Item Dependent Attribute Mapping',self.dependent_attribute_mapping)		
				duplicate_doc = frappe.new_doc("Item Dependent Attribute Mapping")
				duplicate_doc.item = doc.item
				duplicate_doc.dependent_attribute = doc.dependent_attribute
				duplicate_doc.mapping = doc.mapping
				duplicate_doc.details = doc.details
				duplicate_doc.save()
				self.dependent_attribute_mapping = duplicate_doc.name
			
			for bom in self.get('item_bom'):
				if bom.based_on_attribute_mapping and bom.attribute_mapping:
					doc = frappe.get_doc("Item BOM Attribute Mapping", bom.attribute_mapping)
					duplicate_doc = frappe.new_doc("Item BOM Attribute Mapping")
					duplicate_doc.item = self.item
					duplicate_doc.bom_item = bom.item
					duplicate_doc.save()
					bom.attribute_mapping = duplicate_doc.name
				else:
					bom.attribute_mapping = None

		for attribute in self.get('item_attributes'):
			if attribute.mapping == None:
				doc = frappe.new_doc("Item Item Attribute Mapping")
				doc.attribute_name= attribute.attribute 
				doc.save()
				attribute.mapping = doc.name
		
		for bom in self.get('item_bom'):
			if bom.based_on_attribute_mapping and not bom.attribute_mapping:
				doc = frappe.new_doc("Item BOM Attribute Mapping")
				doc.item_production_detail = self.name
				doc.item = self.item
				doc.bom_item = bom.item

				attr_values = []
				item_doc = frappe.get_doc("Item",bom.item)
				for item in item_doc.attributes:
					attr_values.append({'attribute':item.attribute})

				doc.set('item_attributes',[{'attribute':self.packing_attribute}])
				doc.set('bom_item_attributes',attr_values)

				doc.flags.ignore_validate = True
				doc.save()
				bom.attribute_mapping = doc.name
			elif not bom.based_on_attribute_mapping and bom.attribute_mapping:
				name = bom.attribute_mapping
				bom.attribute_mapping = None
				frappe.delete_doc("Item BOM Attribute Mapping", name)

		if not self.is_new():
			if self.packing_combo == 0:
				frappe.throw("The packing combo should not be zero")

			if self.packing_attribute_no == 0:
				frappe.throw("The packing attribute no should not be zero")

			mapping = None
			is_attribute = False
			for item in self.item_attributes:
				if item.attribute == self.packing_attribute:
					is_attribute = True
					mapping = item.mapping
					break

			if not is_attribute:
				frappe.throw("The packing attribute is not the item attribute")

			map_doc = frappe.get_doc("Item Item Attribute Mapping", mapping)
			if len(map_doc.values) < self.packing_attribute_no:
				frappe.throw(f"The Packing attribute no is {self.packing_attribute_no} But there is only {len(map_doc.values)} attributes are available")

			if len(self.packing_attribute_details) != self.packing_attribute_no:
				frappe.throw(f"Only {self.packing_attribute_no} {self.packing_attribute}'s are required")

			attr = set()
			if self.auto_calculate:
				for row in self.packing_attribute_details:
					attr.add(row.attribute_value)
					row.quantity = 0
			else:		
				sum = 0.0
				for row in self.packing_attribute_details:
					if not row.quantity:
						frappe.throw("Zero is not considered as a valid quantity")
					sum = sum + row.quantity
					attr.add(row.attribute_value)

				if sum < self.packing_combo or sum > self.packing_combo:
					frappe.throw(f"The sum of quantity should be {self.packing_combo}")

			if len(attr) != len(self.packing_attribute_details):
				frappe.throw("Duplicate Attribute values are occured")	

	def on_trash(self):
		documents = {
			"Item Item Attribute Mapping":[],
			'Item Dependent Attribute Mapping':[],
			"Item BOM Attribute Mapping":[],
		}
		for attribute in self.get('item_attributes'):
			if attribute.mapping:
				doc_name = attribute.mapping
				attribute.mapping = None
				documents['Item Item Attribute Mapping'].append(doc_name)

		if self.dependent_attribute_mapping:
			doc_name = self.dependent_attribute_mapping
			self.dependent_attribute_mapping = None
			documents['Item Dependent Attribute Mapping'].append(doc_name)		

		for bom in self.get('item_bom'):
			if bom.attribute_mapping:
				doc_name = bom.attribute_mapping
				bom.attribute_mapping = None
				documents["Item BOM Attribute Mapping"].append(doc_name)
		delete_docs(documents)		

def delete_docs(documents):
	for key, value in documents.items():
		doctype = frappe.qb.DocType(key)
		if value:
			frappe.qb.from_(doctype).delete().where(doctype.name.isin(value)).run()

def fetch_set_items(set_items):
	set_items = [item.as_dict() for item in set_items]
	set_item_result ={}
	set_item_result['set_attributes'] = []
	set_item_result['values'] = []
	for key, items in groupby(set_items, lambda i: i['index']):
		items = list(items)
		item_list = {}
		item_list['major_attribute'] = items[0]['major_attribute_value']
		item_list['val'] = {}
		for item in items:
			if item['set_item_attribute_value'] not in set_item_result['set_attributes']:
				set_item_result['set_attributes'].append(item['set_item_attribute_value'])
			item_list['val'][item['set_item_attribute_value']] = item['attribute_value']
		set_item_result['values'].append(item_list)
	return set_item_result

def save_item_details(set_item_detail):
	if isinstance(set_item_detail, string_types):
		set_item_detail = json.loads(set_item_detail)
	item_detail = []
	for idx,item in enumerate(set_item_detail['values']):
		for value in item['val']:
			row = {}
			row['index'] = idx
			row['major_attribute_value'] = item['major_attribute']
			row['set_item_attribute_value'] = value
			row['attribute_value'] = item['val'][value]
			item_detail.append(row)
	return item_detail		

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_item_attributes(doctype, txt, searchfield, start, page_len, filters):
	if (doctype != 'Item Attribute' or filters['item_production_detail'] == None):
		return []

	item_production_detail_name = filters['item_production_detail']
	item_production_detail = frappe.get_doc("Item Production Detail", item_production_detail_name)
	attributes = [attribute.attribute for attribute in item_production_detail.item_attributes]
	return [[value] for value in attributes if value.lower().startswith(txt.lower())]

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_attribute_detail_values(doctype, txt, searchfield, start, page_len, filters):
	doc = frappe.qb.DocType('Item Item Attribute Mapping Value')
	result = frappe.qb.from_(doc).select(doc.attribute_value).where(doc.parent == filters['mapping']).run(as_list=True)
	attr_list = [[res[0]] for res in result if res[0].lower().startswith(txt.lower())]
	return attr_list

@frappe.whitelist()
def get_attribute_values(item_production_detail, attributes = None):
	lot = frappe.get_doc("Item Production Detail", item_production_detail)
	attribute_values = {}

	if not attributes:
		attributes = [attr.attribute for attr in lot.item_attributes]

	for attribute in lot.item_attributes:
		if attribute.attribute in attributes and attribute.mapping != None:
			doc = frappe.get_doc("Item Item Attribute Mapping", attribute.mapping)
			attribute_values[attribute.attribute] = [d.attribute_value for d in doc.values]

	return attribute_values

@frappe.whitelist()
def get_calculated_bom(item_production_detail, items, production_order):
	item_detail = frappe.get_doc("Item Production Detail", item_production_detail)
	bom = {}
	if isinstance(items, string_types):
		items = json.loads(items)
	production_doc = frappe.get_doc("Production Order", production_order)
	pack_out_stage = production_doc.pack_out_stage
	pack_in_stage = production_doc.pack_in_stage
	if len(items) == 0:
		return
	for item in items:
		qty = item['qty']
		if not qty:
			continue
		variant = item['item_variant']
		attr_values = {}
		variant_doc = frappe.get_doc("Item Variant", variant)
		item_name = variant_doc.item
		doc = frappe.get_doc("Item", item_name)
		uom_factor = get_uom_conversion_factor(doc.uom_conversion_details,production_doc.uom,production_doc.packing_uom)
		qty = (qty * uom_factor)
		for x in variant_doc.attributes:
			attr_values[x.attribute] = x.attribute_value
		if len(item_detail.item_bom) == 0:
			frappe.throw("No BOM is set on this item production detail")
		for bom_item in item_detail.item_bom:
			qty_of_product = bom_item.qty_of_product
			qty_of_bom = bom_item.qty_of_bom_item
			if pack_in_stage and pack_out_stage and bom_item.dependent_attribute_value:
				if not bom_item.dependent_attribute_value == pack_in_stage:
					dependent_attr_uom = get_uom(production_doc.dependent_attribute_mapping,bom_item.dependent_attribute_value)
					bom_item_doc = frappe.get_doc("Item", bom_item.item)
					bom_item_conv = get_uom_conversion_factor(bom_item_doc.uom_conversion_details, dependent_attr_uom ,production_doc.packing_uom)
					qty_of_product = bom_item_conv

			qty_of_product = qty_of_product/qty_of_bom

			if not bom_item.based_on_attribute_mapping:
				quantity = qty / qty_of_product
				item_variant = get_or_create_variant(bom_item.item, {})
				if not bom.get(item_variant, False):
					bom[item_variant] = [math.ceil(quantity),bom_item.process_name]
				else:
					bom[item_variant][0] += math.ceil(quantity)
			else:
				pack_attr = item_detail.packing_attribute
				pack_combo = item_detail.packing_combo
				pack_attr_no =	item_detail.packing_attribute_no
				mapping_attr = bom_item.attribute_mapping
				mapping_doc = frappe.get_doc("Item BOM Attribute Mapping", mapping_attr)
				if item_detail.auto_calculate:
					temp_qty = qty/pack_attr_no
				else:
					temp_qty = qty/pack_combo
					
				temp_qty = temp_qty*qty_of_bom

				if item_detail.is_set_item:
					set_attr = item_detail.set_item_attribute
					set_item_map_doc = None
					for attr in item_detail.item_attributes:
						if attr.attribute == set_attr:
							set_item_map_doc = attr.mapping
							break

					same_attribute = get_same_attr(mapping_doc.item_attributes, attr_values, pack_attr)
					if pack_attr in attr_values:
						quantity = qty/qty_of_product
						set_map = frappe.get_doc("Item Item Attribute Mapping", set_item_map_doc)
						for set_val in set_map.values:
							for value in mapping_doc.values:
								if value.attribute == pack_attr and value.attribute_value == attr_values[pack_attr] and value.type == "item":
									if check_attr_value(value.index,'item',mapping_doc.values,set_attr,set_val.attribute_value):
										updated_bom = create_and_update_bom(value.index, "bom", mapping_doc.values, attr_values, mapping_doc.bom_item_attributes,bom_item.item, bom, quantity, bom_item.process_name)
										bom = updated_bom
										break
					else:
						set_map = frappe.get_doc("Item Item Attribute Mapping", set_item_map_doc)
						for pack_attr_value in item_detail.packing_attribute_details:
							for attr in set_map.values:
								for value in mapping_doc.values:
									if value.attribute == set_attr and value.attribute_value == attr.attribute_value and value.type == "item":
										get_attr = pack_attr
										get_value = pack_attr_value.attribute_value

										if not same_attribute == pack_attr:
											get_attr = same_attribute
											get_value = attr_values[same_attribute]	
											
										if item_detail.major_attribute_value == attr.attribute_value:	
											if check_attr_value(value.index, "item", mapping_doc.values,get_attr,get_value):
												attributes = get_same_index_values(value.index, "bom", mapping_doc.values, attr_values, mapping_doc.bom_item_attributes)
												updated_bom = create_and_update_bom_set(attributes,bom_item.item,bom,temp_qty,item_detail.auto_calculate,item_detail.packing_attribute_details, pack_attr_value.attribute_value, bom_item.process_name)
												bom = updated_bom
												break
										else:
											attributes = get_bottom_part_values(get_value,attr.attribute_value, item_detail.set_item_combination_details, item_detail.set_item_attribute, get_attr,mapping_doc.values, attr_values, mapping_doc.bom_item_attributes) 
											for attribute in attributes:
												updated_bom = create_and_update_bom_set(attribute,bom_item.item,bom,temp_qty,item_detail.auto_calculate,item_detail.packing_attribute_details, pack_attr_value.attribute_value, bom_item.process_name)
												bom = updated_bom
											break
				else:
					same_attribute = get_same_attr(mapping_doc.item_attributes, attr_values, pack_attr)
					if pack_attr in attr_values:
						quantity = qty/qty_of_product
						get_attr = pack_attr
						get_value = attr_values[pack_attr]
						if not same_attribute == pack_attr:
							get_attr = same_attribute
							get_value = attr_values[same_attribute]
						for value in mapping_doc.values:
							if value.attribute == get_attr and value.attribute_value == get_value and value.type == "item":
								updated_bom = create_and_update_bom(value.index, "bom", mapping_doc.values, attr_values, mapping_doc.bom_item_attributes,bom_item.item, bom, quantity,bom_item.process_name)	
								bom = updated_bom
								break	
					else:
						item_map_doc = None
						for attr in item_detail.item_attributes:
							if attr.attribute == same_attribute:
								item_map_doc = attr.mapping
								break
						
						item_map = frappe.get_doc("Item Item Attribute Mapping", item_map_doc)
						for attr in item_map.values:
							for value in mapping_doc.values:
								if value.attribute == same_attribute and value.attribute_value == attr.attribute_value and value.type == "item":
									attributes = get_same_index_values(value.index, "bom", mapping_doc.values, attr_values, mapping_doc.bom_item_attributes)
									updated_bom = create_and_update_bom_set(attributes,bom_item.item,bom,temp_qty,item_detail.auto_calculate,item_detail.packing_attribute_details, attr.attribute_value, bom_item.process_name)
									bom = updated_bom
									break
	bom_items = []	
	
	for key, val in bom.items():
		bom_items.append({'item': key,'process_name':val[1],'required_qty':val[0]})

	production_doc.set('bom_summary', bom_items)
	production_doc.last_calculated_time = now_datetime()
	production_doc.save()	

def get_same_attr(item_attributes, attr_values, pack_attr):
	for item in item_attributes:
		if item.attribute == pack_attr:
			return item.attribute

	for item in item_attributes:
		if item.attribute in attr_values:
			return item.attribute
 
def get_uom(dependent_attribute_mapping,dependent_attribute_value):
	dept_attr_details = get_dependent_attribute_details(dependent_attribute_mapping)
	for attr in dept_attr_details['attr_list']:
		if attr == dependent_attribute_value:
			return dept_attr_details['attr_list'][attr]['uom']

def get_bottom_part_values(attr, major_attr, set_item_details, set_item_attr, pack_attr, mapping_doc_values, attr_values, mapping_bom_item_attributes):
	index = -1
	for item in set_item_details:
		if item.major_attribute_value == attr:
			index = item.index
			break

	bottom_parts = {}
	bottom_parts[set_item_attr] = []
	for item in set_item_details:
		if item.index == index and item.set_item_attribute_value == major_attr:
			bottom_parts[set_item_attr].append({set_item_attr : item.set_item_attribute_value, pack_attr:item.attribute_value})

	attributes = []
	for parts in bottom_parts[set_item_attr]:
		key, val = parts.items()
		index = -1
		for x in mapping_doc_values:
			if x.attribute == key[0] and x.attribute_value == key[1] and x.type == 'item':
				for y in mapping_doc_values:
					if y.index == x.index and y.attribute == val[0] and y.attribute_value == val[1] and y.type == 'item':
						index = y.index
		if index != -1:	
			attributes.append(get_same_index_values(index,"bom",mapping_doc_values, attr_values, mapping_bom_item_attributes))
	return attributes

def check_attr_value(index, type, values,attr ,attr_value):
	for value in values:
		if index == value.index and type == value.type and attr == value.attribute and attr_value == value.attribute_value:
			return True
	return False

def get_quantity(packing_attribute_details, attr):
	for item in packing_attribute_details:
		if item.attribute_value == attr:
			return flt(item.quantity)

def get_same_index_values(index, type, values, attr_values, bom_item_attributes):
	bom_attr = {}
	for value in values:
		if value.index == index and value.type == type:
			bom_attr[value.attribute] = value.attribute_value
		elif value.index > index:
			break

	for attr in bom_item_attributes:
		if attr.attribute not in bom_attr and attr.same_attribute:
			bom_attr[attr.attribute] = attr_values[attr.attribute]

	return bom_attr		

def create_and_update_bom(index, type, mapping_doc_values, attr_values, mapping_bom_item_attributes, bom_item, bom, quantity, process_name):
	attributes = get_same_index_values(index, type, mapping_doc_values, attr_values, mapping_bom_item_attributes)
	new_variant = get_or_create_variant(bom_item, attributes)
	if not bom.get(new_variant, False):
		bom[new_variant] = [math.ceil(quantity),process_name]
	else:
		bom[new_variant][0] += math.ceil(quantity)
	return bom

def create_and_update_bom_set(attributes, bom_item, bom, quantity, auto_calculate, packing_attribute_details, attr_value, process_name):
	new_variant = get_or_create_variant(bom_item, attributes)
	if not bom.get(new_variant, False):
		if auto_calculate:
			bom[new_variant] = [math.ceil(quantity),process_name]
		else:
			bom[new_variant] = [math.ceil(quantity * get_quantity(packing_attribute_details, attr_value)),process_name]
	else:
		if auto_calculate:
			bom[new_variant][0] += math.ceil(quantity)
		else:
			bom[new_variant][0] += math.ceil(quantity * get_quantity(packing_attribute_details, attr_value))
			
	return bom

@frappe.whitelist()
def get_new_set_item_details(set_item_attribute_mapping_value, packing_attribute_details, major_attribute_value):
	if isinstance(packing_attribute_details, string_types):
		packing_attribute_details = json.loads(packing_attribute_details)
	doc = frappe.get_doc('Item Item Attribute Mapping', set_item_attribute_mapping_value)
	set_attributes = []
	for item in doc.values:
		set_attributes.append(item.attribute_value)
	set_item_detail = []
	for item in packing_attribute_details:
		item_list = {}
		item_list['major_attribute'] = item['attribute_value']
		item_list['val'] = {}
		for i in set_attributes:
			if i == major_attribute_value:
				item_list['val'][i] = item['attribute_value']
			else:
				item_list['val'][i] = None
		set_item_detail.append(item_list)
	set_item_details = {}
	set_item_details['set_attributes'] = set_attributes
	set_item_details['values'] = set_item_detail
	return set_item_details

@frappe.whitelist()
def get_packing_values(packing_attribute_mapping_value, packing_attribute_no):
	map_doc = frappe.get_doc("Item Item Attribute Mapping", packing_attribute_mapping_value)
	if len(map_doc.values) < int(packing_attribute_no):
		frappe.throw(f"The Packing attribute number is {packing_attribute_no} But there is only {len(map_doc.values)} attributes are available")

	packing_list = []
	for index,attr in enumerate(map_doc.values):
		if index > int(packing_attribute_no) - 1:
			break
		packing_list.append({'attribute_value':attr.attribute_value})
	return packing_list