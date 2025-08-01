frappe.listview_settings["Vendor Bill Tracking"] = {
  onload: (frm) => {
    frm.page.add_action_item(__("Bulk Assign"), async () => {
      let dialog = new frappe.ui.Dialog({
        title: "Bulk Assignment",
        fields: [
          {
            label: "Assign To",
            fieldname: "assign_to",
            fieldtype: "Link",
            options: "Department",
            reqd: 1,
          },
          {
            label: "Remarks",
            fieldname: "remarks",
            fieldtype: "Small Text",
          },
        ],
        primary_action_label: "Assign All",
        primary_action: async (values) => {
          dialog.hide();
          frappe.call({
            method:
              "production_api.production_api.doctype.vendor_bill_tracking.vendor_bill_tracking.bulk_assign_bills",
            args: {
              assign_to: values["assign_to"],
              selected_docs: frm.get_checked_items(),
              remarks: values["remarks"],
            },
            freeze: true,
            freeze_msg: `Bulk Assigning Bills To ${values["user"]}`,
            callback: (r) => {
              cur_list.refresh();
            },
          });
        },
      });
      dialog.show();
    });
  },
  refresh: (frm) => {
    frm.page.add_inner_button(__("Show Assigned To Me"), async () => {
      await frm.filter_area.clear();
      frappe.call({
        method:
          "production_api.production_api.doctype.department.department.get_user_departments",
        callback: async (r) => {
          await frm.filter_area.set([
            ["Vendor Bill Tracking", "assigned_to", "in", r.message],
            ["Vendor Bill Tracking", "docstatus", "=", 1],
            ["Vendor Bill Tracking", "form_status", "!=", "Closed"],
          ]);
          frm.refresh();
        },
      });
    });
  },
};
