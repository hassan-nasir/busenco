import xmlrpc.client
from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)
from itertools import chain

class ResPartner(models.Model):
    _inherit = 'res.partner'

    v8_referance_id = fields.Char(string="V8 refrence Id")



class MigrationScript(models.Model):
    _name = 'custom.migration'
    _description = 'Migration Script'

    @api.model
    def run_migration(self):
        # Odoo v8 source connection details
        source_url = 'http://localhost:2069'
        # source_url = 'http://192.168.46.124:2069'
        source_db = 'BusEnco'
        source_user = 'becadmin'
        source_password = 'admin'

        # Connect to the source database
        source_common = xmlrpc.client.ServerProxy(f"{source_url}/xmlrpc/2/common")
        source_uid = source_common.authenticate(source_db, source_user, source_password, {})
        source_models = xmlrpc.client.ServerProxy(f"{source_url}/xmlrpc/2/object")

        # Migrate customers
        # self._migrate_customers(source_models, source_db, source_uid, source_password)

        # migrate products
        # self._migrate_products(source_models, source_db, source_uid, source_password)

        # migrate taxes
        # self._migrate_taxes(source_models, source_db, source_uid, source_password)

        # Migrate sales orders
        self._migrate_sales_orders(source_models, source_db, source_uid, source_password)

        # Migrate invoices
        # self._migrate_invoices(source_models, source_db, source_uid, source_password)

    # def _get_partners_map(self,source_models, source_db, source_uid, source_password):
    #     """
    #     Returns a dictionary to map partner IDs from Odoo v8 to Odoo v16.
    #     Example: {v8_partner_id: v16_partner_id}
    #     """
    #     partners_map = {}
    #
    #     # Fetch partners from v8 (Odoo v8)
    #     partners_v8 = source_models.execute_kw(
    #         source_db, source_uid, source_password, 'res.partner', 'search_read',
    #         [[]], {'fields': ['id', 'name'],'limit': 5}
    #     )
    #
    #     # Fetch partners from v16 (Odoo v16)
    #     partners_v16 = self.env['res.partner'].search([])  # Adjust as needed for your v16 setup
    #
    #     # Map v8 partners to v16 partners
    #     for partner_v8 in partners_v8:
    #         # Assuming partners are mapped based on name. Adjust according to your needs.
    #         matching_partner_v16 = partners_v16.filtered(lambda p: p.v8_referance_id == str(partner_v8['id']))
    #
    #         if matching_partner_v16:
    #             partners_map[partner_v8['id']] = matching_partner_v16.id
    #
    #     return partners_map

    def _get_partners_map(self, source_models, source_db, source_uid, source_password):
        _logger.info("Fetching partners map...")

        partners_map = {}
        # Fetch partners from Odoo v8
        partners_v8 = source_models.execute_kw(
            source_db, source_uid, source_password, 'res.partner', 'search_read',
            [[]], {'fields': ['id', 'name']}
        )

        for partner in partners_v8:
            partner_id_v8 = partner['id']

            # Look for the partner in v16 using the v8_referance_id field
            partner_v16 = self.env['res.partner'].search([('v8_referance_id', '=', str(partner_id_v8))])

            if partner_v16:
                partners_map[partner_id_v8] = partner_v16.id
            else:
                _logger.warning(f"Partner with v8 ID {partner_id_v8} not found in v16.")

        _logger.debug(f"Partner map: {partners_map}")
        return partners_map

    def _migrate_sales_orders(self, source_models, source_db, source_uid, source_password):
        _logger.info("Starting sales order migration...")

        # Fetch the product mapping from v8 to v16
        product_map = self._get_products_map(source_models, source_db, source_uid, source_password)

        # Fetch sales orders from Odoo v8
        sales_orders = source_models.execute_kw(
            source_db, source_uid, source_password, 'sale.order', 'search_read',
            [[]], {'fields': ['id', 'partner_id', 'date_order', 'origin'], 'limit': 5}
        )

        sales_order_map = {}

        for sales_order in sales_orders:
            sales_order_id_v8 = sales_order['id']
            partner_id_v8 = sales_order.get('partner_id')

            if isinstance(partner_id_v8, list):
                partner_id_v8 = partner_id_v8[0]

            # Map partner_id_v8 to partner_id_v16
            partner_v16 = self.env['res.partner'].search([('v8_referance_id', '=', str(partner_id_v8))], limit=1)

            if not partner_v16:
                _logger.error(f"Partner ID {partner_id_v8} not found in v16. Skipping sales order.")
                continue

            # Prepare sales order data for v16
            sales_order_vals = {
                'partner_id': partner_v16.id,
                'date_order': sales_order.get('date_order'),
                'origin': sales_order.get('origin', ''),
                'state': 'draft',
            }

            created_sales_order = self.env['sale.order'].create(sales_order_vals)
            sales_order_map[sales_order_id_v8] = created_sales_order.id

            # Fetch and create order lines using the mapped product IDs
            sales_order_lines = source_models.execute_kw(
                source_db, source_uid, source_password, 'sale.order.line', 'search_read',
                [[('order_id', '=', sales_order_id_v8)]],
                {'fields': ['id', 'product_id', 'product_uom_qty', 'price_unit', 'tax_id'], 'limit': 5}
            )

            order_line_vals = []
            for line in sales_order_lines:
                order_line_vals.append((0, 0, {
                    'product_id': product_map.get(line['product_id']),
                    'product_uom_qty': line.get('product_uom_qty', 1),
                    'price_unit': line.get('price_unit', 0),
                    'tax_id': [(6, 0, [self._get_taxes_map().get(tax_id) for tax_id in line.get('tax_id', [])])],
                    'order_id': created_sales_order.id,
                }))

            created_sales_order.write({'order_line': order_line_vals})
            _logger.info(f"Added {len(sales_order_lines)} order lines to sales order {created_sales_order.name}")

        return sales_order_map∂

    def _get_products_map(self, source_models, source_db, source_uid, source_password):
        _logger.info("Fetching products from Odoo v8 and mapping them to Odoo v16...")

        # Fetch product details from Odoo v8
        products_v8 = source_models.execute_kw(
            source_db, source_uid, source_password, 'product.product', 'search_read',
            [[]], {'fields': ['id', 'default_code', 'name']}  # Assuming you use 'default_code' as identifier
        )

        # Create a mapping dictionary from v8 product IDs to v16 product IDs
        product_map = {}

        # Iterate over the fetched products and build the mapping
        for product_v8 in products_v8:
            product_id_v8 = product_v8['id']
            default_code_v8 = product_v8.get('default_code')

            # Search for the matching product in Odoo v16 based on 'default_code' or 'name'
            product_v16 = self.env['product.product'].search([('default_code', '=', default_code_v8)], limit=1)

            if product_v16:
                # If a match is found, map the v8 product ID to v16 product ID
                product_map[product_id_v8] = product_v16.id
                _logger.info(f"Mapped v8 product ID {product_id_v8} to v16 product ID {product_v16.id}.")
            else:
                # If no match is found, log the error (you can also handle this differently if needed)
                _logger.warning(
                    f"Product with v8 ID {product_id_v8} (default_code {default_code_v8}) not found in v16.")

        return product_map











    # def _migrate_invoices(self, source_models, source_db, source_uid, source_password):
    #     print("Starting invoice migration...")
    #
    #     # Fetch invoices from the source system (Odoo v8)
    #
    #     domain = [('state', '=', 'open')]  # Example: Fetch only open invoices
    #     offset = 0
    #     limit = 5
    #     fields = ['id', 'partner_id', 'date_invoice', 'amount_total']  # Specify only required fields
    #     invoices = source_models.execute_kw(
    #         source_db, source_uid, source_password, 'account.invoice', 'search_read',
    #         [domain], {'fields': fields, 'limit': limit, 'offset': offset}
    #     )
    #     _logger.info(f"Fetched invoices: {len(invoices)}")
    #
    #     # Prepare mappings for partner, product, taxes, accounts, and journals
    #     partners_map = self._get_partners_map()  # Function to map partner IDs from v8 to v16
    #     products_map = self._get_products_map()  # Function to map product IDs from v8 to v16
    #     taxes_map = self._get_taxes_map()  # Function to map tax IDs from v8 to v16
    #     accounts_map = self._get_accounts_map()  # Function to map account codes from v8 to v16
    #     # journals_map = self._get_journals_map()  # Function to map journal names from v8 to v16
    #     currencies_map = self._get_currencies_map()  # Function to map currency names from v8 to v16
    #
    #     for invoice in invoices:
    #         # Prepare invoice values for migration
    #         partner_id = partners_map.get(invoice['partner_id'][0])
    #         # journal_name = invoice['journal_id'][1]  # Assuming journal is in the format (id, name)
    #         # journal_id = journals_map.get(journal_name)
    #         # currency_id = currencies_map.get(invoice['currency_id'][1])  # Assuming currency is in the format (id, name)
    #
    #         # Mapping invoice type (sale or purchase)
    #         move_type = 'out_invoice' if invoice['type'] == 'out_invoice' else 'in_invoice'
    #
    #         # Prepare invoice header data
    #         invoice_vals = {
    #             'partner_id': partner_id,
    #             # 'journal_id': journal_id,
    #             # 'currency_id': currency_id,
    #             'invoice_date': invoice['date_invoice'],
    #             'move_type': move_type,
    #             'invoice_line_ids': [],
    #             'invoice_origin': invoice.get('origin', ''),
    #             'payment_term_id': invoice.get('payment_term_id', False),  # Optional
    #         }
    #
    #         # Add invoice lines
    #         for line in invoice['invoice_line']:
    #             product_id = products_map.get(line[0])  # Assuming line[0] contains product ID
    #             tax_ids = [(6, 0, [taxes_map.get(tax_id) for tax_id in line[3]])]  # Assuming line[3] contains tax_ids
    #             account_id = accounts_map.get(line[5])  # Assuming line[5] contains account code
    #
    #             invoice_vals['invoice_line_ids'].append((0, 0, {
    #                 'product_id': product_id,
    #                 'quantity': line[2],  # Assuming line[2] contains quantity
    #                 'price_unit': line[4],  # Assuming line[4] contains price_unit
    #                 'tax_ids': tax_ids,
    #                 'account_id': account_id,
    #                 'name': line[1],  # Assuming line[1] contains the description
    #             }))
    #
    #         # Check if the invoice already exists in v16 (based on invoice origin or other unique fields)
    #         existing_invoice = self.env['account.move'].search([('invoice_origin', '=', invoice['origin'])], limit=1)
    #
    #         if not existing_invoice:
    #             # Create new invoice
    #             new_invoice = self.env['account.move'].create(invoice_vals)
    #             _logger.info(f"Created invoice {new_invoice.name}")
    #         else:
    #             _logger.info(f"Invoice already exists: {existing_invoice.name}")
    #
    # def _get_partners_map(self):
    #     # Fetch all partners from Odoo v16 and map partner ids from v8 to v16
    #     partners_v8 = self.env['res.partner'].search([])  # Fetch all partners from Odoo v16
    #     partners_map = {}
    #
    #     for partner in partners_v8:
    #         # Map partner ID from Odoo v8 (source) to Odoo v16 (target)
    #         partners_map[partner.id] = partner.id  # You may customize this mapping logic as needed
    #
    #     return partners_map
    #
    # def _get_products_map(self):
    #     # Fetch all products from Odoo v16 and map product IDs from v8 to v16
    #     products_v16 = self.env['product.product'].search([])  # Fetch all products from Odoo v16
    #     products_map = {}
    #
    #     for product in products_v16:
    #         # Map product ID from Odoo v8 (source) to Odoo v16 (target)
    #         products_map[product.id] = product.id  # You may customize this mapping logic as needed
    #
    #     return products_map
    #
    # def _get_taxes_map(self):
    #     # Fetch all taxes from Odoo v16 and map tax IDs from v8 to v16
    #     taxes_v16 = self.env['account.tax'].search([])  # Fetch all taxes from Odoo v16
    #     taxes_map = {}
    #
    #     for tax in taxes_v16:
    #         # Map tax ID from Odoo v8 (source) to Odoo v16 (target)
    #         taxes_map[tax.id] = tax.id  # You may customize this mapping logic as needed
    #
    #     return taxes_map
    #
    # def _get_accounts_map(self):
    #     # Fetch all accounts from Odoo v16 and map account codes from v8 to v16
    #     accounts_v16 = self.env['account.account'].search([])  # Fetch all accounts from Odoo v16
    #     accounts_map = {}
    #
    #     for account in accounts_v16:
    #         # Map account code from Odoo v8 (source) to Odoo v16 (target)
    #         accounts_map[account.code] = account.id  # You may customize this mapping logic as needed
    #
    #     return accounts_map
    #
    # def _get_journals_map(self):
    #     # Fetch all journals from Odoo v16 and map journal names from v8 to v16
    #     journals_v16 = self.env['account.journal'].search([])  # Fetch all journals from Odoo v16
    #     journals_map = {}
    #
    #     for journal in journals_v16:
    #         # Map journal name from Odoo v8 (source) to Odoo v16 (target)
    #         journals_map[journal.name] = journal.id  # You may customize this mapping logic as needed
    #
    #     return journals_map
    #
    # def _get_currencies_map(self):
    #     # Fetch all currencies from Odoo v16 and map currency names from v8 to v16
    #     currencies_v16 = self.env['res.currency'].search([])  # Fetch all currencies from Odoo v16
    #     currencies_map = {}
    #
    #     for currency in currencies_v16:
    #         # Map currency name from Odoo v8 (source) to Odoo v16 (target)
    #         currencies_map[currency.name] = currency.id  # You may customize this mapping logic as needed
    #
    #     return currencies_map

    # def _migrate_taxes(self, source_models, source_db, source_uid, source_password):
    #     print("Starting tax migration...")
    #
    #     # Fetch taxes from the source system
    #     taxes = source_models.execute_kw(
    #         source_db, source_uid, source_password, 'account.tax', 'search_read', [[]]
    #     )
    #     _logger.info(f"Fetched taxes: {len(taxes)}")
    #
    #     # Define a mapping for the `type_tax_use` field
    #     type_tax_use_map = {
    #         'sale': 'sale',
    #         'purchase': 'purchase',
    #         'none': 'none',  # Default in v16 for taxes used in both sale and purchase
    #         'all': 'none',  # Map 'all' from v8 to 'none' in v16
    #     }
    #
    #     for tax in taxes:
    #         # Prepare tax values for migration
    #         tax_vals = {
    #             'name': tax['name'],
    #             'amount': tax['amount'],
    #             'amount_type': 'percent' if tax['type'] == 'percent' else 'fixed',
    #             'type_tax_use': type_tax_use_map.get(tax['type_tax_use'], 'none'),  # Map with fallback to 'none'
    #             'active': tax.get('active', True),
    #             'description': tax.get('description', ''),
    #         }
    #
    #         # Log unexpected `type_tax_use` values
    #         if tax['type_tax_use'] not in type_tax_use_map:
    #             _logger.warning(
    #                 f"Unexpected type_tax_use: {tax['type_tax_use']} for tax {tax['name']}. Defaulting to 'none'.")
    #
    #         # Map tax group if it exists
    #         if 'tax_group_id' in tax and tax['tax_group_id']:
    #             tax_group_name = source_models.execute_kw(
    #                 source_db, source_uid, source_password, 'account.tax.group', 'read', [tax['tax_group_id']]
    #             )[0]['name']
    #             tax_group = self.env['account.tax.group'].search([('name', '=', tax_group_name)], limit=1)
    #             if tax_group:
    #                 tax_vals['tax_group_id'] = tax_group.id
    #
    #         # Check if the tax already exists in v16
    #         existing_tax = self.env['account.tax'].search([('name', '=', tax['name'])], limit=1)
    #         if not existing_tax:
    #             new_tax = self.env['account.tax'].create(tax_vals)
    #             _logger.info(f"Created tax: {new_tax.name}")
    #         else:
    #             _logger.info(f"Tax already exists: {existing_tax.name}")




    def _migrate_products(self, source_models, source_db, source_uid, source_password):
        print("Starting product migration...")

        # Fetch products from the source system
        products = source_models.execute_kw(
            source_db, source_uid, source_password, 'product.template', 'search_read', [[]]
        )
        _logger.info(f"Fetched products: {len(products)}")

        for product in products:
            # Prepare product values
            product_vals = {
                'name': product['name'],
                'type': product['type'],
                'default_code': product.get('default_code', ''),
                'list_price': product.get('list_price', 0.0),
                'standard_price': product.get('standard_price', 0.0),
                'uom_id': self._map_uom(product['uom_id'][0]),  # Map Unit of Measure
                'uom_po_id': self._map_uom(product['uom_po_id'][0]),  # Map Purchase Unit of Measure
                'categ_id': self._map_category(product['categ_id'][0]),  # Map Category
            }

            # Check if the product already exists in the target database
            existing_product = self.env['product.template'].search(
                [('name', '=', product['name']), ('default_code', '=', product.get('default_code', ''))], limit=1
            )
            if not existing_product:
                self.env['product.template'].create(product_vals)
                _logger.info(f"Created product: {product['name']}")
            else:
                _logger.info(f"Product already exists: {product['name']}")

    def _map_uom(self, source_uom_id):
        """
        Map Unit of Measure (UoM) from the source database to the target database.
        """
        if not source_uom_id:
            return False

        source_uom = self.env['uom.uom'].search([('id', '=', source_uom_id)], limit=1)
        if source_uom:
            target_uom = self.env['uom.uom'].search([('name', '=', source_uom.name)], limit=1)
            if target_uom:
                return target_uom.id
        return False

    def _map_category(self, source_categ_id):
        """
        Map Product Category from the source database to the target database.
        """
        if not source_categ_id:
            return False

        source_category = self.env['product.category'].search([('id', '=', source_categ_id)], limit=1)
        if source_category:
            target_category = self.env['product.category'].search([('name', '=', source_category.name)], limit=1)
            if target_category:
                return target_category.id
        return False






    def _migrate_customers(self, source_models, source_db, source_uid, source_password):
        print("Starting customer migration...")

        # Fetch customers from the source system
        customers = source_models.execute_kw(
            source_db, source_uid, source_password, 'res.partner', 'search_read', [[]]
        )
        _logger.info(f"Fetched customers: {len(customers)}")

        for customer in customers:
            # Create or fetch the parent contact
            parent_contact_vals = {
                'name': customer['name'],
                'email': customer.get('email', ''),
                'phone': customer.get('phone', ''),
                'street': customer.get('street', ''),
                'v8_referance_id': customer.get('id'),
            }

            parent_contact = self.env['res.partner'].search(
                [('name', '=', customer['name']), ('email', '=', customer.get('email', ''))], limit=1
            )
            if not parent_contact:
                parent_contact = self.env['res.partner'].create(parent_contact_vals)
                _logger.info(f"Created parent contact: {parent_contact.name}")
            else:
                _logger.info(f"Parent contact already exists: {parent_contact.name}")

            # Check if the customer has child contacts
            if 'child_ids' in customer and customer['child_ids']:
                # Fetch unique child contacts from source
                child_contacts = source_models.execute_kw(
                    source_db, source_uid, source_password,
                    'res.partner', 'search_read', [[('id', 'in', list(set(customer['child_ids'])))]]
                    # Ensure uniqueness
                )
                _logger.info(f"Fetched {len(child_contacts)} child contacts for {parent_contact.name}")

                # Create child contacts for the parent, if they don't already exist
                for child_contact in child_contacts:
                    existing_child_contact = self.env['res.partner'].search(
                        [('name', '=', child_contact['name']), ('parent_id', '=', parent_contact.id)], limit=1
                    )
                    if not existing_child_contact:
                        child_contact_vals = {
                            'name': child_contact['name'],
                            'email': child_contact.get('email', ''),
                            'phone': child_contact.get('phone', ''),
                            'street': child_contact.get('street', ''),
                            'v8_referance_id': child_contact.get('id'),
                            'parent_id': parent_contact.id,  # Link to the parent contact
                        }
                        self.env['res.partner'].create(child_contact_vals)
                        _logger.info(
                            f"Created child contact: {child_contact['name']} under parent {parent_contact.name}")
                    else:
                        _logger.info(
                            f"Child contact already exists: {child_contact['name']} under parent {parent_contact.name}")









