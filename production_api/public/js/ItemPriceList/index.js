import PriceList from "./itempricelist.vue";

export default class ItemPriceList {
    constructor({ wrapper } = {}) {
        this.$wrapper = $(wrapper);
        this.make_body();
    }
    
    make_body() {
        this.$page_container = $('<div class="item-price-list-template frappe-control">').appendTo(this.$wrapper);
        this.vue = new Vue({
            el: '.item-price-list-template',
            render: h => h(PriceList, {
            }),
        });
    }
}
