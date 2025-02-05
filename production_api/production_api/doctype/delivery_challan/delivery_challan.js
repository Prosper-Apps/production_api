// Copyright (c) 2024, Essdee and contributors
// For license information, please see license.txt

frappe.ui.form.on("Delivery Challan", {
    setup(frm){
        frm.set_query('from_address', function(doc) {
			if(!doc.from_location) {
				frappe.throw(__("Please set {0}",[__(frappe.meta.get_label(doc.doctype, 'supplier', doc.name))]));
			}
			return {
				query: 'frappe.contacts.doctype.address.address.address_query',
				filters: {
					link_doctype: 'Supplier',
					link_name: doc.from_location
				}
			};
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
    },
    refresh(frm){
		frm.page.btn_secondary.hide()
        frm.set_query('work_order',() => {
            return {
                filters : {
                    "docstatus" : 1,
                    "is_delivered" : 0,
                    "open_status":"Open",
                }
            }
        })
        $(frm.fields_dict['deliverable_items'].wrapper).html("")
        if(frm.doc.__onload && frm.doc.__onload.deliverable_item_details) {
            frm.doc['deliverable_item_details'] = JSON.stringify(frm.doc.__onload.deliverable_item_details);
            frm.deliverable_items = new frappe.production.ui.Delivery_Challan(frm.fields_dict['deliverable_items'].wrapper,frm.doc.__onload.deliverable_item_details )
            frm.deliverable_items.update_status();
        }
		frm.calculated = false
		if(!frm.is_new() && frm.doc.docstatus == 0){
			frm.add_custom_button("Calculate", function(){
				frappe.call({
					method: "production_api.production_api.doctype.delivery_challan.delivery_challan.get_calculated_items",
					args: {
						doc_name: frm.doc.name,
						work_order: frm.doc.work_order,
					},
					callback: async function (r) {
						let d = new frappe.ui.Dialog({
							size: "large",
							fields: [
								{
									fieldname: "calculated_items_html",
									fieldtype: "HTML",
								},
							],
							primary_action() {
								frm.trigger("calculate_deliverables")
								d.hide()
							},
						});
						frm.calculate_deliverables = new frappe.production.ui.WorkOrderItemView(d.fields_dict.calculated_items_html.wrapper)
						await frm.calculate_deliverables.load_data(r.message)
						frm.calculate_deliverables.create_input_attributes()
						d.show()						
					},
				});
			})
		}

		if(frm.doc.docstatus == 1){
			if(!frm.doc.transfer_complete && frm.doc.is_internal_unit){
				frm.add_custom_button("Transfer Complete", ()=> {
					frappe.call({
						method:"production_api.production_api.doctype.delivery_challan.delivery_challan.construct_stock_entry_details",
						args: {
							doc_name : frm.doc.name,
						},
						callback: function(r){
							frappe.set_route("Form","Stock Entry",r.message)
						}
					})
				})
			}
			frm.add_custom_button("Cancel", ()=> {
				frm._cancel()
			})
		}
    },
	work_order:function(frm) {
        frm.doc.items = [];
        $(frm.fields_dict['deliverable_items'].wrapper).html("")
        if (! frm.doc.work_order){
            return;
        }
        else{
            frappe.call({
                method:"production_api.production_api.doctype.delivery_challan.delivery_challan.get_deliverables",
                args:{
                    "work_order": frm.doc.work_order,
                },
                callback: function(response){
                    if(response.message){
                        frm.deliverable_items = new frappe.production.ui.Delivery_Challan(frm.fields_dict['deliverable_items'].wrapper, response.message.items)
                        frm.set_value('supplier',response.message.supplier)
                        frm.set_value('supplier_address',response.message.supplier_address)        
                    }
                }
            })
        }
	},
	calculate_deliverables(frm){
		let items = frm.calculate_deliverables.get_work_order_items()
		frappe.call({
			method:'production_api.production_api.doctype.delivery_challan.delivery_challan.get_calculated_deliverables',
			args: {
				items: items,
				wo_name: frm.doc.work_order,
				doc_name: frm.doc.name,
				deliverable:true
			},
			freeze:true,
			freeze_message: __("Calculate Deliverables..."),
			callback: function(r){
				// frappe.call({
				// 	// method:"production_api.production_api.doctype.delivery_challan"
				// })
				let items = r.message
				for(let i = 0 ; i < frm.doc.items.length ; i++){
					for (let j = 0 ; j < items.length ; j++){
						if(frm.doc.items[i]['item_variant'] == items[j]['item_variant']){
							frm.doc.items[i]['delivered_quantity'] = items[j]['qty']
							break
						}
					}
				}
				frm.dirty()
				frm.calculated = true
				frm.save()
			}
		})
	},
    validate: function(frm){
		if(!frm.calculated){
			let deliverables = frm.deliverable_items.get_data()
        	frm.doc['deliverable_item_details'] = JSON.stringify(deliverables)
		}
		else{
			frm.doc['deliverable_item_details'] = null
		}
    },
	from_location: function(frm) {
		if (frm.doc.from_location) {
			frappe.production.ui.eventBus.$emit("supplier_updated", frm.doc.from_location)
		}
		if (frm.doc.from_location) {
			frappe.call({
				method: "production_api.production_api.doctype.supplier.supplier.get_primary_address",
				args: {
					"supplier": frm.doc.from_location
				},
				callback: function(r) {
					if (r.message) {
						frm.set_value('from_address', r.message)
					}
					else{
						frm.set_value("from_address","")
					}
				}
			})
		}
		else{
			frm.set_value("from_address","")
		}
	},
	supplier: function(frm) {
		if (frm.doc.supplier) {
			frappe.production.ui.eventBus.$emit("supplier_updated", frm.doc.supplier)
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
					else{
						frm.set_value('supplier_address', '')
					}
				}
			})
		}
		else{
			frm.set_value('supplier_address', '')

		}
	},
    from_address: function(frm) {
		if (frm.doc['from_address']) {
			frappe.call({
				method: "production_api.production_api.doctype.purchase_order.purchase_order.get_address_display",
				args: {
					"address_dict": frm.doc['from_address'] 
				},
				callback: function(r) {
					if (r.message) {
						frm.set_value('from_address_details', r.message)
					}
					else{
						frm.set_value('from_address_details', '');
					}
				}
			})
		} 
		else {
			frm.set_value('from_address_details', '');
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
						frm.set_value('supplier_address_details', r.message)
					}
					else{
						frm.set_value('supplier_address_details', '');
					}
				}
			})
		} 
		else {
			frm.set_value('supplier_address_details', '');
		}
	},
});
