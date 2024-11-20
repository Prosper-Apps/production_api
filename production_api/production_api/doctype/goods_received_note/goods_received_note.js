// Copyright (c) 2023, Essdee and contributors
// For license information, please see license.txt
frappe.ui.form.on('Goods Received Note', {
	setup: function(frm) {
		frm.set_query('against_id', function(doc) {
			let filters = {
				'docstatus': 1,
				"open_status":"Open"
			}
			if (doc.supplier) {
				filters['supplier'] = doc.supplier
			}
			if (doc.against == 'Purchase Order') {
				filters['status'] = ['in', ['Ordered', 'Partially Delivered', 'Overdue', 'Partially Cancelled']]
			}
			return{
				filters: filters
			}
		});
		frm.set_query('supplier_address', function(doc) {
			if(!doc.supplier) {
				frappe.throw(__("Please set {0}",[__(frappe.meta.get_label(doc.doctype, 'supplier', doc.name))]));
			}
			return {
				query: 'frappe.contacts.doctype.address.address.address_query',
				filters: {
					link_doctype: 'Supplier',
					link_name: doc.supplier
				}
			};
		});
		frm.set_query('delivery_address', function(doc) {
			if(!doc.delivery_location) {
				frappe.throw(__("Please set {0}",[__(frappe.meta.get_label(doc.doctype, 'delivery_location', doc.name))]));
			}
			return {
				query: 'frappe.contacts.doctype.address.address.address_query',
				filters: {
					link_doctype: 'Supplier',
					link_name: doc.delivery_location
				}
			};
		});
		frm.set_query('billing_address', function(doc) {
			if(!doc.delivery_location) {
				frappe.throw(__("Please set {0}",[__(frappe.meta.get_label(doc.doctype, 'delivery_location', doc.name))]));
			}
			return {
				query: 'frappe.contacts.doctype.address.address.address_query',
				filters: {
					link_doctype: 'Supplier',
					link_name: doc.delivery_location
				}
			};
		});
		frm.set_query('contact_person', function(doc) {
			if(!doc.supplier) {
				frappe.throw(__("Please set {0}",[__(frappe.meta.get_label(doc.doctype, 'supplier', doc.name))]));
			}
			return {
				query: 'frappe.contacts.doctype.contact.contact.contact_query',
				filters: {
					link_doctype: 'Supplier',
					link_name: doc.supplier
				}
			};
		});
	},
	onload:async function(frm) {
		if (frm.is_new() && frm.doc.against_id && frm.doc.against == "Work Order") {
			await frm.trigger("against")
			frm.trigger("against_id")
		}
	},
	refresh: function(frm) {
		$(frm.fields_dict['item_html'].wrapper).html("");
		if(frm.doc.against == 'Purchase Order'){
			
			frm.itemEditor = new frappe.production.ui.GRNPurchaseOrder(frm.fields_dict["item_html"].wrapper);
			frm.itemEditor.load_data({
				supplier: frm.doc.supplier,
				against: frm.doc.against,
				against_id: frm.doc.against_id
			}, true);
			if(frm.doc.__onload && frm.doc.__onload.item_details) {
				frm.doc['item_details'] = JSON.stringify(frm.doc.__onload.item_details);
				frm.itemEditor.load_data({
					items: frm.doc.__onload.item_details,
				}, true);
			}
		}
		else{
			frm.itemEditor = new frappe.production.ui.GRNWorkOrder(frm.fields_dict["item_html"].wrapper);
			frm.itemEditor.load_data({
				supplier: frm.doc.supplier,
				against: frm.doc.against,
				against_id: frm.doc.against_id
			}, true);
			if( frm.doc.__onload && frm.doc.__onload.item_details && frm.doc.__onload.item_delivered_details) {
				frm.doc['item_details'] = JSON.stringify(frm.doc.__onload.item_details);	
				frm.doc['item_delivered_details'] = JSON.stringify(frm.doc.__onload.item_delivered_details)
				frm.itemEditor.load_data({
					items: frm.doc.__onload.item_details,
					delivered_items: frm.doc.__onload.item_delivered_details
				}, true);	
			}
		}
		frm.itemEditor.update_status();
		frappe.production.ui.eventBus.$on("grn_updated", e => {
			frm.dirty();
			frm.events.save_item_details(frm);
		})
		if (frm.doc.docstatus == 0) {
			var print_menu = $(".dropdown-menu > li:contains('Print')");
			if (print_menu.length > 0){
				print_menu[0].parentElement.removeChild(print_menu[0]);
			}
			var print_btn = $('[data-original-title="Print"]');
			if(print_btn.length > 0){
				print_btn[0].parentElement.removeChild(print_btn[0]);
			}
		}
		if(frm.doc.docstatus == 1 && frm.doc.against == "Work Order" && frm.doc.rework_created == 0){
			frm.add_custom_button("Create Rework",()=> {
				let d =new frappe.ui.Dialog({
					title : "Select the type of rework",
					fields: [
						{
							"fieldname":"supplier_type",
							"fieldtype":"Select",
							"label":"Supplier Type",
							"options":"Same Supplier\nDifferent Supplier",
							"reqd":true,
						},
						{
							"fieldname":"rework_type",
							"fieldtype":"Select",
							"label":"Rework Type",
							"options":"No Cost\nNet Cost Nil\nAdditional Cost",
							"reqd":true,
						},
					],
					primary_action(values){
						if(values.supplier_type == 'Different Supplier'){
							d.hide()
							let dialog = new frappe.ui.Dialog({
								title:"Select Supplier",
								fields: [
									{
										"fieldname":"supplier",
										"fieldtype":"Link",
										"options":"Supplier",
										"label":"Supplier",
									},
									{
										"fieldname":"supplier_address",
										"fieldtype":"Link",
										"options":"Address",
										"label":"Supplier Address",
									}
								],
								primary_action(val){
									dialog.hide()
									make_rework(frm, val.supplier, val.supplier_address, frm.doc.delivery_address, values.rework_type, values.supplier_type)
								}
							})
							dialog.show()
						}
						else{
							d.hide()
							make_rework(frm, frm.doc.supplier, frm.doc.supplier_address, frm.doc.delivery_address, values.rework_type, values.supplier_type)
						}
					}
				})
				d.show()
			})
		}
	},
	save_item_details: function(frm) {
		if(frm.itemEditor){
			let items = frm.itemEditor.get_items();
			if(items && items.length > 0 && frm.doc.against == "Work Order") {
				frm.doc['item_details'] = JSON.stringify(items[0]);
				frm.doc['item_delivered_details'] = JSON.stringify(items[1])
			}
			else if(items && items.length > 0 && frm.doc.against == "Purchase Order"){
				frm.doc['item_details'] = JSON.stringify(items);
			}
			else {
				frm.doc['item_details'] = null;
			}
		}
	},
	validate: function(frm) {
		if(frm.itemEditor){
			frm.events.save_item_details(frm);
		}
		else {
			frappe.throw(__('Please refresh and try again.'));
		}
	},
	supplier: function(frm) {
		if (frm.doc.supplier) {
			if(frm.doc.against == 'Purchase Order'){
				frappe.production.ui.eventBus.$emit("update_grn_details", {against: frm.doc.against})
			}
			else{
				frappe.production.ui.eventBus.$emit("update_grn_work_details", {against: frm.doc.against})
			}
		}
		if (frm.doc.supplier) {
			frappe.call({
				method: "production_api.production_api.doctype.supplier.supplier.get_primary_address",
				args: {
					"supplier": frm.doc.supplier
				},
				callback: function(r) {
					if (r.message) {
						frm.set_value('supplier_address', r.message)
					} 
				}
			})
		}
	},
	delivery_location: function(frm) {
		if (frm.doc.delivery_location) {
			frappe.call({
				method: "production_api.production_api.doctype.supplier.supplier.get_primary_address",
				args: {
					"supplier": frm.doc.delivery_location
				},
				callback: function(r) {
					if (r.message) {
						frm.set_value('delivery_address', r.message)
					} 
					else {
						frm.set_value('delivery_address', '')
					}
				}
			})
		}
	},
	against: function(frm) {
		frm.refresh()
		if(frm.doc.against == 'Purchase Order'){
			frappe.production.ui.eventBus.$emit("update_grn_details", {against: frm.doc.against})
		}
		else{
			frappe.production.ui.eventBus.$emit("update_grn_work_details", {against: frm.doc.against})
		}
		
	},
	against_id: function(frm) {
		if(frm.doc.against == 'Purchase Order'){
			frappe.production.ui.eventBus.$emit("update_grn_details", {against_id: frm.doc.against_id})
		}
		else{
			frappe.production.ui.eventBus.$emit("update_grn_work_details", {against_id: frm.doc.against_id})
		}
		if (frm.doc.against_id) {
			if(frm.doc.against == 'Purchase Order'){
				frappe.db.get_doc(frm.doc.against, frm.doc.against_id).then(doc => {
					frm.set_value('supplier', doc.supplier);
					frm.set_value('delivery_location', doc.default_delivery_location);
				})
			}
			else{
				frappe.db.get_doc(frm.doc.against, frm.doc.against_id).then(doc => {
					frm.set_value('supplier', doc.supplier);
					frm.set_value('supplier_address', doc.supplier_address);
				})
			}
		} 
		else {
			frm.set_value('supplier', '');
			frm.set_value('delivery_location', '');
		}
	},
	supplier_address: function(frm) {
		if (frm.doc['supplier_address']) {
			frappe.call({
				method: "production_api.production_api.doctype.purchase_order.purchase_order.get_address_display",
				args: {
					"address_dict": frm.doc['supplier_address'] 
				},
				callback: function(r) {
					if (r.message) {
						frm.set_value('supplier_address_display', r.message)
					}
				}
			})
		} 
		else {
			frm.set_value('supplier_address_display', '');
		}
	},
	delivery_address: function(frm) {
		if (frm.doc['delivery_address']) {
			frappe.call({
				method: "production_api.production_api.doctype.purchase_order.purchase_order.get_address_display",
				args: {
					"address_dict": frm.doc['delivery_address'] 
				},
				callback: function(r) {
					if (r.message) {
						frm.set_value('delivery_address_display', r.message)
					}
				}
			})
		} 
		else {
			frm.set_value('delivery_address_display', '');
		}
	},
	billing_address: function(frm) {
		if (frm.doc['billing_address']) {
			frappe.call({
				method: "frappe.contacts.doctype.address.address.get_address_display",
				args: {
					"address_dict": frm.doc['billing_address'] 
				},
				callback: function(r) {
					if (r.message) {
						frm.set_value('billing_address_display', r.message)
					}
				}
			})
		} 
		else {
			frm.set_value('billing_address_display', '');
		}
	},
	contact_person: function(frm) {
		if (frm.doc["contact_person"]) {
			frappe.call({
				method: "frappe.contacts.doctype.contact.contact.get_contact_details",
				args: {
					contact: frm.doc.contact_person 
				},
				callback: function(r) {
					if (r.message){
						frm.set_value(r.message);
					}
				}
			})
		}
	},
});

function make_rework(frm, supplier, supplier_address, delivery_address, rework_type, supplier_type){
	frappe.call({
		method:"production_api.production_api.doctype.goods_received_note.goods_received_note.get_grn_rework_items",
		args: {
			doc_name:frm.doc.name,
		},
		callback: function(r){
			if(r.message){
				let x = frappe.model.get_new_doc('Work Order');
				x.is_rework = true;
				x.parent_wo = frm.doc.against_id;
				x.work_order = frm.doc.name;
				x.naming_series = "WO-";
				x.supplier = supplier;
				x.process_name = r.message.process_name;
				x.planned_start_date = r.message.planned_start_date;
				x.planned_end_date = r.message.planned_end_date;
				x.expected_delivery_date = r.message.expected_delivery_date;
				x.item = r.message.item;
				x.lot = r.message.lot;
				x.supplier_address = supplier_address;
				x.delivery_address = delivery_address;
				x.open_status = r.message.open_status;
				x.deliverables = r.message.items;
				x.receivables = r.message.items;
				x.wo_date = frappe.datetime.nowdate();
				x.rework_type = rework_type;
				x.supplier_type = supplier_type;
				frappe.set_route("Form",x.doctype, x.name);
			}
			else{
				frappe.msgprint("There is no mistake items are received")
			}
		}
	})
}
