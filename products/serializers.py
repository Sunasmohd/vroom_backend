from rest_framework import serializers

from core.serializers import UserAddressSerializer
from .models import *
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone



class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'title','image']
        
class CustomizationHeaderSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomizationHeader
        fields = ['id', 'title', 'max_selection', 'is_required']

class CustomizationChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomizationChoice
        fields = ['id', 'title', 'price','is_veg']

class CustomizationChoiceWithPriceSerializer(serializers.ModelSerializer):
    customization_choice = CustomizationChoiceSerializer(read_only=True)
    parent_choice = serializers.IntegerField(allow_null=True)
    price = serializers.DecimalField(decimal_places=2,max_digits=8)
    is_base = serializers.SerializerMethodField()
    original_price = serializers.DecimalField(decimal_places=2, max_digits=8)  # OG price
    
    class Meta:
        model = CustomizationPriceRule
        fields = ['id', 'customization_choice', 'parent_choice', 'price', 'is_base', 'original_price']
        
    def get_is_base(self,obj):
        return obj['is_base']

class CustomizationSerializer(serializers.ModelSerializer):
    customization_header = CustomizationHeaderSerializer( read_only=True)
    choices = serializers.SerializerMethodField()

    class Meta:
        model = ProductCustomizationHeader
        fields = ['customization_header', 'sort_order', 'choices']

    # def get_choices(self, obj):
    #     # Get all price rules and unavailable choices for this product
    #     product = obj.product
    #     price_rules = CustomizationPriceRule.objects.filter(product=product).select_related('customization_choice', 'customization_price_rules_self')
    #     unavailable = ProductChoicesUnavailablility.objects.filter(product=product).values_list('customization_choice', flat=True)
    #     price_rule_choices = {rule.customization_choice.id for rule in price_rules}

    #     # Get all choices for this header
    #     all_choices = CustomizationChoice.objects.filter(customization_header=obj.customization_header)
    #     result = []
    #     # Add choices from price rules
    #     for rule in price_rules:
    #         if rule.customization_choice.customization_header == obj.customization_header:
    #             result.append({
    #                 'customization_choice': rule.customization_choice,
    #                 'parent_choice': rule.customization_price_rules_self.customization_choice.id if rule.customization_price_rules_self else None,
    #                 'price': rule.price,
    #                 'is_base': rule.is_base,
    #             })

    #     # Add remaining choices from CustomizationChoice if not in price rules or unavailable
    #     for choice in all_choices:
    #         if choice.id not in price_rule_choices and choice.id not in unavailable:
    #             result.append({
    #                 'customization_choice': choice,
    #                 'parent_choice': None,
    #                 'price': choice.price,
    #                 'is_base': rule.is_base,
    #             })

    #     return CustomizationChoiceWithPriceSerializer(result, many=True).data

    def get_choices(self, obj):
        from decimal import Decimal
        product = obj.product
        active_flash_sale = Offer.get_active_flash_sale()
        price_rules = CustomizationPriceRule.objects.filter(product=product).select_related(
            'customization_choice', 'customization_price_rules_self'
        )
        unavailable = ProductChoicesUnavailablility.objects.filter(product=product).values_list(
            'customization_choice', flat=True
        )
        price_rule_choices = {rule.customization_choice.id for rule in price_rules}
        all_choices = CustomizationChoice.objects.filter(customization_header=obj.customization_header)
        result = []

        # Check if this header is in the offer's applicable_headers
        applies_discount = (
            active_flash_sale and
            obj in active_flash_sale.applicable_headers.all()
        )

        # Add choices from price rules
        for rule in price_rules:
            if rule.customization_choice.customization_header == obj.customization_header:
                original_price = rule.price
                price = rule.price
                if applies_discount:
                    discount = (
                        product.flash_sale_discount
                        if product.flash_sale_discount is not None
                        else active_flash_sale.discount_value if active_flash_sale else None
                    )
                    is_percentage = (
                        product.flash_sale_is_percentage
                        if product.flash_sale_discount is not None
                        else active_flash_sale.is_percentage if active_flash_sale else False
                    )
                    if discount is not None:
                        if is_percentage:
                            effective_discount = Decimal(str(discount))
                            if obj.max_discount and obj.is_percentage:
                                effective_discount = min(effective_discount, Decimal(str(obj.max_discount)))
                            price = rule.price * (1 - effective_discount / 100)
                        else:
                            if obj.max_discount:
                                max_flat = (rule.price * Decimal(str(obj.max_discount)) / 100
                                            if obj.is_percentage else Decimal(str(obj.max_discount)))
                                price = rule.price - min(Decimal(str(discount)), max_flat)
                            else:
                                price = rule.price - Decimal(str(discount))
                result.append({
                    'customization_choice': rule.customization_choice,
                    'parent_choice': (rule.customization_price_rules_self.customization_choice.id
                                     if rule.customization_price_rules_self else None),
                    'price': max(price, Decimal('0.00')),
                    'original_price':original_price,
                    'is_base': rule.is_base,
                })

        # Add remaining choices from CustomizationChoice
        for choice in all_choices:
            if choice.id not in price_rule_choices and choice.id not in unavailable:
                original_price = choice.price
                price = choice.price
                if applies_discount:
                    discount = (
                        product.flash_sale_discount
                        if product.flash_sale_discount is not None
                        else active_flash_sale.discount_value if active_flash_sale else None
                    )
                    is_percentage = (
                        product.flash_sale_is_percentage
                        if product.flash_sale_discount is not None
                        else active_flash_sale.is_percentage if active_flash_sale else False
                    )
                    if discount is not None:
                        if is_percentage:
                            effective_discount = Decimal(str(discount))
                            if obj.max_discount and obj.is_percentage:
                                effective_discount = min(effective_discount, Decimal(str(obj.max_discount)))
                            price = choice.price * (1 - effective_discount / 100)
                        else:
                            if obj.max_discount:
                                max_flat = (choice.price * Decimal(str(obj.max_discount)) / 100
                                            if obj.is_percentage else Decimal(str(obj.max_discount)))
                                price = choice.price - min(Decimal(str(discount)), max_flat)
                            else:
                                price = choice.price - Decimal(str(discount))
                result.append({
                    'customization_choice': choice,
                    'parent_choice': None,
                    'price': max(price, Decimal('0.00')),
                    'original_price':original_price,
                    'is_base': False,
                })

        return CustomizationChoiceWithPriceSerializer(result, many=True).data
    
class ExpandableHeaderSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpandableHeader
        fields = ['id', 'title']

class ExpandableChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpandableChoices
        fields = ['id', 'title', 'price', 'is_veg']

class DealProductCreationSerializer(serializers.Serializer):
    product = serializers.IntegerField()  # Explicitly expect an integer PK
    quantity = serializers.IntegerField(min_value=1, default=1)

    def validate_product(self, value):
        # Ensure the product exists in the Product table
        if not Product.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"Product with id {value} does not exist.")
        return value

    def create(self, validated_data):
        deal = self.context['deal']
        product = validated_data['product']
        quantity = validated_data.get('quantity', 1)
        
        # Create multiple DealProduct instances
        instances = []
        for _ in range(quantity):
            instance = DealProduct(deal=deal, product=product)  # Use product for ForeignKey
            instance.save()
            instances.append(instance)
        return instances
    

class DealCreationSerializer(serializers.ModelSerializer):
    products = DealProductCreationSerializer(many=True, write_only=True)

    class Meta:
        model = Deal
        fields = ['title', 'price', 'is_expandable', 'products']

    def create(self, validated_data):
        products_data = validated_data.pop('products', [])
        deal = Deal.objects.create(**validated_data)
        
        for product_data in products_data:
            serializer = DealProductCreationSerializer(data=product_data, context={'deal': deal})
            serializer.is_valid(raise_exception=True)
            serializer.save()
        
        return deal
    
class DealProductSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='product.id', read_only=True)
    deal_product_id = serializers.IntegerField(source='id', read_only=True)
    title = serializers.CharField(source='product.title', read_only=True)
    description = serializers.CharField(source='product.description', read_only=True)
    image = serializers.CharField(source='product.image.url', read_only=True, allow_null=True)
    category = CategorySerializer(source='product.category', read_only=True)
    is_veg = serializers.BooleanField(source='product.is_veg', read_only=True)
    is_customizable = serializers.BooleanField(source='product.is_customizable', read_only=True)
    price = serializers.DecimalField(source='product.price', max_digits=7, decimal_places=2, read_only=True)
    customizations = serializers.SerializerMethodField()
    expandable_customizations = serializers.SerializerMethodField()
    branch_availability = serializers.SerializerMethodField()

    class Meta:
        model = DealProduct
        fields = ['id','deal_product_id', 'description','title', 'image','category', 'is_veg', 'price', 'is_customizable', 'customizations', 'expandable_customizations','branch_availability']

    def get_branch_availability(self, obj):
        # if not obj.is_active:
        #     return {"status": "unavailable", "message": "Product discontinued"}
        
        branch_ids = self.context.get('branch_ids', [])
        if not branch_ids:
            return {"status": "available", "message": "In stock"}

        # Count the number of branches provided
        total_branches = len(branch_ids)
        
        # Fetch all stock records for this product across the provided branch_ids
        stocks = ProductBranchStock.objects.filter(branch_id__in=branch_ids, product=obj.product)
        
        # If no records exist, all branches have it available by default
        if not stocks.exists():
            return {"status": "available", "message": "In stock"}

        # Count branches with explicit unavailability or out-of-stock status
        unavailable_count = 0
        for stock in stocks:
            status = stock.get_availability_status()
            if status['status'] in ['unavailable', 'out_of_stock']:
                unavailable_count += 1
            # Early exit: If we find a branch with availability, stop and return
            elif status['status'] == 'available':
                return {"status": "available", "message": "In stock"}

        # If the number of unavailable/out-of-stock records equals the number of branches,
        # the product is unavailable across all specified branches
        if unavailable_count == total_branches:
            # Return the first status as a representative (could be out_of_stock or unavailable)
            return stocks.first().get_availability_status()

        # If fewer than all branches have a record, at least one branch has it available
        return {"status": "available", "message": "In stock"}
    
    
    def get_customizations(self, obj):
        if hasattr(obj.product, 'is_customizable') and obj.product.is_customizable:
            product_customizations = ProductCustomizationHeader.objects.filter(product=obj.product)
            
            return CustomizationSerializer(product_customizations, many=True).data
        return []

    def get_expandable_customizations(self, obj):
        # # Otherwise, fetch product-specific expandable customizations
        # category_choices = ExpandableChoices.objects.filter(
        #     category=obj.product.category, deal__isnull=True, base_product__isnull=True, is_deal_global=False
        # )
        
        # product_choices = ExpandableChoices.objects.filter(
        #     base_product=obj.product, deal__isnull=True, is_deal_global=False
        # )
        
        # expandable_headers = ExpandableHeader.objects.filter(
        #     id__in=(category_choices | product_choices).values_list('expandable_header', flat=True).distinct()
        # )
        return []
        # return ExpandableCustomizationSerializer(expandable_headers, many=True, context={'product': obj.product}).data
    
    
    
class DealSerializer(serializers.ModelSerializer):
    expandable_customizations = serializers.SerializerMethodField()
    image = serializers.ImageField(read_only=True, allow_null=True)  # Return image URL
    branch_availability = serializers.SerializerMethodField()
    branch_price = serializers.SerializerMethodField()
    products = serializers.SerializerMethodField()
    flash_sale_price = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True, allow_null=True)
    has_flash_sale = serializers.BooleanField(read_only=True)
    is_best_seller = serializers.BooleanField(read_only=True)
    is_new = serializers.BooleanField(read_only=True)
    is_popular = serializers.BooleanField(read_only=True)

    class Meta:
        model = Deal
        fields = ['id','is_new','is_popular','is_best_seller', 'title','description','image', 'price', 'is_active', 'is_expandable', 'products', 'expandable_customizations','branch_price','branch_availability','flash_sale_price', 'has_flash_sale']

    def get_products(self, obj):
        branch_ids = self.context.get('branch_ids', [])
        deal_products = obj.dealproduct_set.all()
        if branch_ids:
            # Fetch all ProductBranchStock records for products in this deal
            product_ids = deal_products.values_list('product__id', flat=True)
            product_stocks = ProductBranchStock.objects.filter(
                branch_id__in=branch_ids,
                product_id__in=product_ids
            )

            # Determine availability for each product
            product_availability = {}
            total_branches = len(branch_ids)
            for product_id in product_ids:
                
                stocks_for_product = product_stocks.filter(product_id=product_id)
                total_branches_with_stock = stocks_for_product.count()
                unavailable_count = sum(1 for stock in stocks_for_product if not stock.is_available)

                # Exclude if unavailable at all branches
                if total_branches_with_stock == total_branches and unavailable_count == total_branches:
                    product_availability[product_id] = False
                else:
                    product_availability[product_id] = True

            # Filter out unavailable products
            available_product_ids = [pid for pid, available in product_availability.items() if available]
            deal_products = deal_products.filter(product__id__in=available_product_ids)

        return DealProductSerializer(deal_products, many=True, context=self.context).data
    
    def get_branch_availability(self, obj):
        # if not obj.is_active:
        #     return {"status": "unavailable", "message": "Product discontinued"}
        
        branch_ids = self.context.get('branch_ids', [])
        if not branch_ids:
            return {"status": "available", "message": "In stock"}

        # Count the number of branches provided
        total_branches = len(branch_ids)
        
        # Use the filtered products from get_products
        products_data = self.get_products(obj)  # Re-use filtered products
        if not products_data:
            return {"status": "unavailable", "message": "No available products in this deal"}

        all_products_unavailable = True
        for product in products_data:
            product_availability = product['branch_availability']
            if product_availability['status'] == 'available':
                all_products_unavailable = False
                break

        if all_products_unavailable:
            return products_data[0]['branch_availability']

        # If all products are unavailable or out of stock across all branches
        # if all_products_unavailable:
        #     # Return the availability of the first product as a representative status
        # Fetch all stock records for this product across the provided branch_ids
        stocks = DealBranchStock.objects.filter(branch_id__in=branch_ids, deal_id=obj.id)
        
        # If no records exist, all branches have it available by default
        if not stocks.exists():
            return {"status": "available", "message": "In stock"}

        # Count branches with explicit unavailability or out-of-stock status
        unavailable_count = 0
        for stock in stocks:
            status = stock.get_availability_status()
            if status['status'] in ['unavailable', 'out_of_stock']:
                unavailable_count += 1
            # Early exit: If we find a branch with availability, stop and return
            elif status['status'] == 'available':
                return {"status": "available", "message": "In stock"}

        # If the number of unavailable/out-of-stock records equals the number of branches,
        # the product is unavailable across all specified branches
        if unavailable_count == total_branches:
            # Return the first status as a representative (could be out_of_stock or unavailable)
            return stocks.first().get_availability_status()

        # If fewer than all branches have a record, at least one branch has it available
        return {"status": "available", "message": "In stock"}

    def get_branch_price(self, obj):
        branch_id = self.context.get('branch_id')
        if branch_id:
            stock = DealBranchStock.objects.filter(branch_id=branch_id, deal=obj).first()
            return stock.price if stock and stock.price is not None else obj.price
        return obj.price
    
    def get_expandable_customizations(self, obj):
        if not obj.is_expandable:
            return []

        deal_choices = ExpandableChoices.objects.filter(deal=obj, is_deal_global=False)
        global_choices = ExpandableChoices.objects.filter(deal__isnull=True, is_deal_global=True)
        expandable_headers = ExpandableHeader.objects.filter(
            id__in=(deal_choices | global_choices).values_list('expandable_header', flat=True).distinct()
        )
        return ExpandableCustomizationSerializer(expandable_headers, many=True, context={'deal': obj}).data
        
        # # Pass context to DealProductSerializer about whether expandable_customizations is populated
        # self.context['deal_has_expandable'] = bool(expandable_data)  # True if not empty
        # return expandable_data

   
    
    
class ExpandableCustomizationSerializer(serializers.ModelSerializer):
    expandable_header = serializers.SerializerMethodField()
    choices = serializers.SerializerMethodField()

    class Meta:
        model = ExpandableHeader
        fields = ['expandable_header', 'choices']

    def get_expandable_header(self, obj):
        return ExpandableHeaderSerializer(obj, read_only=True).data

    def get_choices(self, obj):
        product = self.context.get('product')
        deal = self.context.get('deal')

        if deal:  # Deal context
            # Deal-specific options (deal matches)
            deal_choices = ExpandableChoices.objects.filter(
                deal=deal, is_deal_global=False, expandable_header=obj.id
            )
            # Global deal options (deal null, is_deal_global=True)
            global_choices = ExpandableChoices.objects.filter(
                deal__isnull=True, is_deal_global=True, expandable_header=obj.id
            )
            choices = deal_choices | global_choices
            
        elif product:  # Single product context ("Make it a Meal")
            # Category-level options (deal null, is_deal_global=False)
            category_choices = ExpandableChoices.objects.filter(
                category=product.category, deal__isnull=True, base_product__isnull=True, is_deal_global=False, expandable_header=obj.id
            )
            # Product-specific options (base_product matches product)
            product_choices = ExpandableChoices.objects.filter(
                base_product=product, deal__isnull=True, is_deal_global=False, expandable_header=obj.id
            )
            choices = category_choices | product_choices
        else:
            choices = ExpandableChoices.objects.none()

        return ExpandableChoiceSerializer(choices, many=True).data
    
 
    
class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ['id', 'user', 'booking_date', 'party_size', 'status', 'notes', 'branch', 'created_at', 'updated_at']
        
class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = ['id', 'payment_type', 'provider', 'last_four','expiry_month','expiry_year', 'is_default', 'created_at']

class TransactionSerializer(serializers.ModelSerializer):
    payment_method = PaymentMethodSerializer(read_only=True)
    class Meta:
        model = Transaction
        fields = ['id', 'order', 'booking', 'payment_method', 'amount', 'status', 'transaction_id', 'created_at', 'completed_at']
        
class CancellationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cancellation
        fields = ['id', 'order', 'booking', 'reason', 'cancelled_at', 'refund_amount']
        

  
class ProductDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    customizations = CustomizationSerializer(source='productcustomizationheader_set', many=True, read_only=True)
    expandable_customizations = serializers.SerializerMethodField()
    image = serializers.ImageField(read_only=True, allow_null=True)  # Return image
    branch_availability = serializers.SerializerMethodField()
    branch_price = serializers.SerializerMethodField()
    flash_sale_price = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True, allow_null=True)
    has_flash_sale = serializers.BooleanField(read_only=True)
    is_best_seller = serializers.BooleanField(read_only=True)
    is_new = serializers.BooleanField(read_only=True)
    is_popular = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = ['id','is_new','is_popular','is_best_seller','title','description', 'image', 'category', 'is_veg','is_customizable', 'price', 'customizations', 'expandable_customizations','branch_price', 'branch_availability', 'flash_sale_price', 'has_flash_sale']
    
    
    
    
    def get_branch_availability(self, obj):
        # if not obj.is_active:
        #     return {"status": "unavailable", "message": "Product discontinued"}
        
        branch_ids = self.context.get('branch_ids', [])
        if not branch_ids:
            return {"status": "available", "message": "In stock"}

        # Count the number of branches provided
        total_branches = len(branch_ids)
        # Fetch all stock records for this product across the provided branch_ids
        stocks = ProductBranchStock.objects.filter(branch_id__in=branch_ids, product=obj)
        # If no records exist, all branches have it available by default
        if not stocks.exists():
            return {"status": "available", "message": "In stock"}

        # Count branches with explicit unavailability or out-of-stock status
        unavailable_count = 0
        for stock in stocks:
            status = stock.get_availability_status()
            if status['status'] in ['unavailable', 'out_of_stock']:
                unavailable_count += 1
            # Early exit: If we find a branch with availability, stop and return
            elif status['status'] == 'available':
                return {"status": "available", "message": "In stock"}
        # If the number of unavailable/out-of-stock records equals the number of branches,
        # the product is unavailable across all specified branches
        if unavailable_count == total_branches:
            # Return the first status as a representative (could be out_of_stock or unavailable)
            return stocks.first().get_availability_status()

        # If fewer than all branches have a record, at least one branch has it available
        return {"status": "available", "message": "In stock"}

    def get_branch_price(self, obj):
        branch_id = self.context.get('branch_id')
        if branch_id:
            stock = ProductBranchStock.objects.filter(branch_id=branch_id, product=obj).first()
            return stock.price if stock and stock.price is not None else obj.price
        return obj.price
    
    def get_expandable_customizations(self, obj):
        # Fetch headers for single product "Make it a Meal" options
        category_choices = ExpandableChoices.objects.filter(
            category=obj.category, deal__isnull=True, base_product__isnull=True, is_deal_global=False
        )
        product_choices = ExpandableChoices.objects.filter(
            base_product=obj, deal__isnull=True, is_deal_global=False
        )
        expandable_headers = ExpandableHeader.objects.filter(
            id__in=(category_choices | product_choices).values_list('expandable_header', flat=True).distinct()
        )
        return ExpandableCustomizationSerializer(expandable_headers, many=True, context={'product': obj}).data
        

 
class FavoriteSerializer(serializers.ModelSerializer):
    product = ProductDetailSerializer(read_only=True, allow_null=True)
    deal = DealSerializer(read_only=True, allow_null=True)
    product_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    deal_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Favorite
        fields = ['id', 'product', 'deal', 'product_id', 'deal_id', 'created_at']
        read_only_fields = ['created_at']

    def validate(self, data):
        product_id = data.get('product_id')
        deal_id = data.get('deal_id')

        if product_id and deal_id:
            raise serializers.ValidationError("Only one of product_id or deal_id can be provided.")
        if not product_id and not deal_id:
            raise serializers.ValidationError("Either product_id or deal_id must be provided.")

        if product_id and not Product.objects.filter(id=product_id).exists():
            raise serializers.ValidationError(f"Product with id {product_id} does not exist.")
        if deal_id and not Deal.objects.filter(id=deal_id).exists():
            raise serializers.ValidationError(f"Deal with id {deal_id} does not exist.")

        return data

    def create(self, validated_data):
        product_id = validated_data.pop('product_id', None)
        deal_id = validated_data.pop('deal_id', None)
        user = self.context['request'].user

        favorite = Favorite(
            user=user,
            product=Product.objects.get(id=product_id) if product_id else None,
            deal=Deal.objects.get(id=deal_id) if deal_id else None,
        )
        favorite.save()
        return favorite

class MenuItemSerializer(serializers.ModelSerializer):
    # product = serializers.IntegerField(source='product.id', read_only=True, allow_null=True)
    # deal = serializers.IntegerField(source='deal.id', read_only=True, allow_null=True)
    product = ProductDetailSerializer(read_only=True, allow_null=True)
    deal = DealSerializer(read_only=True, allow_null=True)

    title = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    is_veg = serializers.SerializerMethodField(read_only=True)
    is_expandable = serializers.SerializerMethodField(read_only=True)
    branch_availability = serializers.SerializerMethodField()
    flash_sale_price = serializers.SerializerMethodField()
    has_flash_sale = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = ['id', 'product', 'deal', 'image', 'title', 'price','has_flash_sale', 'flash_sale_price', 'is_veg', 'is_expandable', 'branch_availability']

    def get_image(self, obj):
        if obj.product:
            return obj.product.image.url
        elif obj.deal:
            return obj.deal.image.url
        return None

    def get_title(self, obj):
        if obj.product:
            return obj.product.title
        elif obj.deal:
            return obj.deal.title
        return None
    
    def get_has_flash_sale(self,obj):
        if obj.product:
            return obj.product.has_flash_sale
        elif obj.deal:
            return obj.deal.has_flash_sale

    def get_price(self, obj):
        branch_ids = self.context.get('branch_ids')
        if branch_ids:
            if obj.product:
                stocks = ProductBranchStock.objects.filter(branch_id__in=branch_ids, product=obj.product)
                prices = [stock.price for stock in stocks if stock.price is not None]
                return min(prices) if prices else obj.product.price
            elif obj.deal:
                stocks = DealBranchStock.objects.filter(branch_id__in=branch_ids, deal=obj.deal)
                prices = [stock.price for stock in stocks if stock.price is not None]
                return min(prices) if prices else obj.deal.price
        return obj.product.price if obj.product else obj.deal.price if obj.deal else None
    
    def get_flash_sale_price(self, obj):
        branch_ids = self.context.get('branch_ids')
        if branch_ids:
            if obj.product and obj.product.has_flash_sale:
                stocks = ProductBranchStock.objects.filter(branch_id__in=branch_ids, product=obj.product)
                prices = [stock.price for stock in stocks if stock.price is not None]
                return min(prices) if prices else obj.product.flash_sale_price
            elif obj.deal and obj.deal.has_flash_sale:
                stocks = DealBranchStock.objects.filter(branch_id__in=branch_ids, deal=obj.deal)
                prices = [stock.price for stock in stocks if stock.price is not None]
                return min(prices) if prices else obj.deal.flash_sale_price
        elif obj.product.has_flash_sale:
            return obj.product.flash_sale_price   
        elif obj.product.has_flash_sale:
            return obj.product.flash_sale_price   
        return None


    def get_is_veg(self, obj):
        if obj.product:
            return obj.product.is_veg
        return False

    def get_is_expandable(self, obj):
        if obj.deal:
            return obj.deal.is_expandable
        return False

    def get_branch_availability(self, obj):
        branch_ids = self.context.get('branch_ids', [])
        if not branch_ids:
            return {"status": "available", "message": "In stock"}
        
        # Simplified: Assume filtering happens in MenuSerializer
        # Just return a status for display purposes, not for filtering
        total_branches = len(branch_ids)
        
        if obj.product:
            stocks = ProductBranchStock.objects.filter(branch_id__in=branch_ids, product_id=obj.product)
            if not stocks.exists():
                return {"status": "available", "message": "In stock"}
            for stock in stocks:
                status = stock.get_availability_status()
                if status['status'] == 'available':
                    return {"status": "available", "message": "In stock"}
            return stocks.first().get_availability_status()

        elif obj.deal:
            deal_stocks = DealBranchStock.objects.filter(branch_id__in=branch_ids, deal_id=obj.deal)
            if not deal_stocks.exists():
                return {"status": "available", "message": "In stock"}
            for stock in deal_stocks:
                status = stock.get_availability_status()
                if status['status'] == 'available':
                    return {"status": "available", "message": "In stock"}
            return deal_stocks.first().get_availability_status()
        
class MenuSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()

    class Meta:
        model = Menu
        fields = ['id', 'title', 'items']

    def get_items(self, obj):
        branch_ids = self.context.get('branch_ids', None)
        items = obj.menuitem_set.all()

        if branch_ids:
            total_branches = len(branch_ids)

            # Step 1: Filter out products unavailable or out of stock at all branches
            product_items = items.filter(product__isnull=False)
            product_ids = product_items.values_list('product__id', flat=True)
            product_stocks = ProductBranchStock.objects.filter(
                branch_id__in=branch_ids,
                product_id__in=product_ids
            )

            product_availability = {}
            for product_id in product_ids:
                stocks_for_product = product_stocks.filter(product_id=product_id)
                total_branches_with_stock = stocks_for_product.count()
                
                if total_branches_with_stock == 0:
                    product_availability[product_id] = True
                else:
                    unavailable_count = 0
                    for stock in stocks_for_product:
                        status = stock.get_availability_status()
                        if status['status'] in ['unavailable', 'out_of_stock']:
                            unavailable_count += 1
                    if total_branches_with_stock == total_branches and unavailable_count == total_branches:
                        product_availability[product_id] = False
                    else:
                        product_availability[product_id] = True

            unavailable_product_ids = [pid for pid, available in product_availability.items() if not available]
            items = items.exclude(product__id__in=unavailable_product_ids)

            # Step 2: Filter out deals unavailable or out of stock at all branches, or with all products unavailable/out of stock
            deal_items = items.filter(deal__isnull=False)
            deal_ids = deal_items.values_list('deal__id', flat=True)
            deal_stocks = DealBranchStock.objects.filter(
                branch_id__in=branch_ids,
                deal_id__in=deal_ids
            )

            deal_availability = {}
            for deal_id in deal_ids:
                deal_stocks_for_deal = deal_stocks.filter(deal_id=deal_id)
                total_branches_with_deal_stock = deal_stocks_for_deal.count()
                
                if total_branches_with_deal_stock == 0:
                    deal_availability[deal_id] = True
                else:
                    deal_unavailable_count = 0
                    for stock in deal_stocks_for_deal:
                        status = stock.get_availability_status()
                        if status['status'] in ['unavailable', 'out_of_stock']:
                            deal_unavailable_count += 1
                    if total_branches_with_deal_stock == total_branches and deal_unavailable_count == total_branches:
                        deal_availability[deal_id] = False
                    else:
                        deal_availability[deal_id] = True

            # For deals that are available, check their products
            potentially_available_deal_ids = [did for did, available in deal_availability.items() if available]
            deal_products = DealProduct.objects.filter(deal_id__in=potentially_available_deal_ids)
            product_ids_in_deals = deal_products.values_list('product__id', flat=True)

            product_stocks_in_deals = ProductBranchStock.objects.filter(
                branch_id__in=branch_ids,
                product_id__in=product_ids_in_deals
            )

            product_availability_in_deals = {}
            for product_id in product_ids_in_deals:
                stocks_for_product = product_stocks_in_deals.filter(product_id=product_id)
                total_branches_with_stock = stocks_for_product.count()
                
                if total_branches_with_stock == 0:
                    product_availability_in_deals[product_id] = True
                else:
                    unavailable_count = 0
                    for stock in stocks_for_product:
                        status = stock.get_availability_status()
                        if status['status'] in ['unavailable', 'out_of_stock']:
                            unavailable_count += 1
                    if total_branches_with_stock == total_branches and unavailable_count == total_branches:
                        product_availability_in_deals[product_id] = False
                    else:
                        product_availability_in_deals[product_id] = True

            # Exclude deals where all products are unavailable or out of stock
            unavailable_deal_ids = []
            for deal_id in potentially_available_deal_ids:
                deal_product_ids = deal_products.filter(deal_id=deal_id).values_list('product__id', flat=True)
                all_unavailable = all(not product_availability_in_deals.get(pid, True) for pid in deal_product_ids)
                if all_unavailable:
                    unavailable_deal_ids.append(deal_id)

            # Combine deal-level and product-level unavailability
            final_unavailable_deal_ids = [did for did, available in deal_availability.items() if not available] + unavailable_deal_ids
            items = items.exclude(deal__id__in=final_unavailable_deal_ids)

        return MenuItemSerializer(items, many=True, context=self.context).data
    
        
class BranchSerializer(serializers.ModelSerializer):
    is_open = serializers.SerializerMethodField()

    class Meta:
        model = Branch
        fields = [
            'id', 'name', 'address', 'city', 'state', 'postal_code', 'country',
            'phone_number', 'latitude', 'longitude', 'is_active', 'opening_time',
            'closing_time', 'delivery_radius', 'min_order_amount', 'delivery_fee',
            'is_open'
        ]

    def get_is_open(self, obj):
        return obj.is_open()


class SpecialSuggestionsBranchWiseSerializer(serializers.ModelSerializer):
    product = ProductDetailSerializer(read_only=True, allow_null=True)
    deal = DealSerializer(read_only=True, allow_null=True)
    branch = BranchSerializer(read_only=True)

    class Meta:
        model = SpecialSuggestionsBranchWise
        fields = ['id', 'product', 'deal', 'branch']
    
class ProductBranchStockSerializer(serializers.ModelSerializer):
    product = ProductDetailSerializer(read_only=True)
    availability_status = serializers.SerializerMethodField()

    class Meta:
        model = ProductBranchStock
        fields = ['id', 'product', 'is_available', 'is_out_of_stock', 'out_of_stock_from', 'out_of_stock_until', 'price', 'availability_status']

    def get_availability_status(self, obj):
        return obj.get_availability_status()

class DealBranchStockSerializer(serializers.ModelSerializer):
    deal = DealSerializer(read_only=True)
    availability_status = serializers.SerializerMethodField()

    class Meta:
        model = DealBranchStock
        fields = ['id', 'deal', 'is_available', 'is_out_of_stock', 'out_of_stock_from', 'out_of_stock_until', 'price', 'availability_status']

    def get_availability_status(self, obj):
        return obj.get_availability_status()
    
    
        
class OfferSerializer(serializers.ModelSerializer):
    free_products = ProductDetailSerializer(many=True, read_only=True)
    free_deals = DealSerializer(many=True, read_only=True)
    applicable_products = ProductDetailSerializer(many=True, read_only=True)
    applicable_deals = DealSerializer(many=True, read_only=True)
    
    class Meta:
        model = Offer
        fields = ['id', 'code', 'offer_type','description', 'discount_value', 'min_spend', 'max_discount', 'auto_apply', 'near_unlock_threshold','usage_scope','per_user_limit','usage_count','usage_limit',
                  'free_products','free_deals', 'applicable_products', 'applicable_deals','is_percentage']

class CartOfferSerializer(serializers.ModelSerializer):
    offer = OfferSerializer(read_only=True)

    class Meta:
        model = CartOffer
        fields = ['offer', 'applied_by_user']
        
class CartItemCustomizationSerializer(serializers.ModelSerializer):
    customization_choice = CustomizationChoiceSerializer(read_only=True)  # Nested serializer

    class Meta:
        model = CartItemCustomization
        fields = ['id', 'price', 'customization_choice_id', 'customization_choice', 'original_price', 'deal_product_id']  # Include full choice object

class CartItemExpandableChoiceSerializer(serializers.ModelSerializer):
    expandable_choice = ExpandableChoiceSerializer(read_only=True)  # Nested serializer
    deal_product = DealProductSerializer(read_only=True)

    class Meta:
        model = CartItemExpandableChoice
        fields = ['id', 'price', 'expandable_choice_id', 'expandable_choice', 'deal_product_id']  # Include full choice object
        
class CartItemSerializer(serializers.ModelSerializer):
    product = ProductDetailSerializer(read_only=True)
    deal = DealSerializer(read_only=True)
    customizations = CartItemCustomizationSerializer(source='cartitemcustomization_set', many=True, read_only=True)
    expandable_choices = CartItemExpandableChoiceSerializer(source='cartitemexpandablechoice_set', many=True, read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    original_subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)  # New field
    
    class Meta:
        model = CartItem
        fields = ['id', 'cart_id','product', 'deal', 'quantity', 'subtotal', 'original_subtotal', 'customizations', 'expandable_choices', 'is_free','unit_price','unit_sale_price',]

class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(source='cartitem_set', many=True, read_only=True)
    applied_offers = CartOfferSerializer(source='cartoffer_set', many=True, read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    original_subtotal = serializers.SerializerMethodField()  # Total original price before flash sale
    discount_amount = serializers.SerializerMethodField()  # Includes flash sale savings
    delivery_fee = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    tax_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    base_total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    def get_original_subtotal(self, obj):
        return sum(item.original_subtotal for item in obj.cartitem_set.all()) or Decimal('0.00')

    def get_discount_amount(self, obj):
        return obj.discount_amount
        # original = self.get_original_subtotal(obj)
        # discounted = obj.subtotal
        
        # return max((original - discounted) + obj.discount_amount, Decimal('0.00'))  # Flash sale + other offer discounts

    class Meta:
        model = Cart
        fields = ['id','base_total', 'user', 'subtotal', 'original_subtotal', 'discount_amount', 'delivery_fee', 'tax_amount', 'total', 'items', 'applied_offers']


class OrderItemCustomizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItemCustomization
        fields = ['customization_choice', 'price']

class OrderItemExpandableChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItemExpandableChoice
        fields = ['expandable_choice', 'price']

class OrderItemSerializer(serializers.ModelSerializer):
    product = ProductDetailSerializer(read_only=True)
    deal = DealSerializer(read_only=True)
    customizations = OrderItemCustomizationSerializer(source='orderitemcustomization_set', many=True, read_only=True)
    expandable_choices = OrderItemExpandableChoiceSerializer(source='orderitemexpandablechoice_set', many=True, read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'deal', 'quantity', 'unit_price', 'unit_sale_price','subtotal', 'customizations', 'expandable_choices','is_free']

# serializers.py
class OrderOfferSerializer(serializers.ModelSerializer):
    offer = OfferSerializer(read_only=True)

    class Meta:
        model = OrderOffer
        fields = ['offer', 'discount_amount']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(source='orderitem_set', many=True, read_only=True)
    offers = OrderOfferSerializer(source='orderoffer_set', many=True, read_only=True)  # Replace single offer field
    address = UserAddressSerializer()
    
    class Meta:
        model = Order
        fields = ['id', 'user', 'address', 'offers','scheduled_at', 'status', 'subtotal', 'discount_amount', 'delivery_fee', 'tax_amount', 'total_amount', 'payment_status', 'created_at', 'updated_at', 'items']


class InvoiceSerializer(serializers.ModelSerializer):
    order = OrderSerializer(read_only=True)
    cancellation = serializers.SerializerMethodField()
    class Meta:
        model = Invoice
        fields = ['id', 'order', 'booking', 'invoice_number', 'total_amount', 'status', 'issued_at', 'paid_at','cancellation']
    
    def get_cancellation(self, obj):
        if obj.order:
            cancellation = Cancellation.objects.filter(order=obj.order).first()
            if cancellation:
                return CancellationSerializer(cancellation).data
        return None


class OrderCreateSerializer(serializers.ModelSerializer):
    cart_id = serializers.IntegerField(write_only=True)
    address_id = serializers.IntegerField(write_only=True)
    scheduled_at = serializers.DateTimeField(required=False, allow_null=True)  # Optional scheduling
    class Meta:
        model = Order
        fields = ['cart_id', 'address_id', 'scheduled_at']

    def create(self, validated_data):
        cart_id = validated_data['cart_id']
        address_id = validated_data['address_id']
        scheduled_at = validated_data.get('scheduled_at')  # Get optional scheduled_at
        user = self.context['request'].user

        if isinstance(user, AnonymousUser):
            raise serializers.ValidationError("User must be logged in to place an order")

        cart = Cart.objects.get(id=cart_id)
        address = UserAddress.objects.get(id=address_id, user=user)

        # Merge cart if it was anonymous
        if not cart.user:
            cart.user = user
            cart.save()

        cart_offers = cart.cartoffer_set.all()  # Get all applied offers
        subtotal = cart.subtotal
        discount_amount_list = cart.discount_amount  # List of {'code': ..., 'amount': ...}
        total_discount = sum(d['amount'] for d in discount_amount_list)  # Sum the amounts
        total_discount_not_flash = sum(
            d['amount'] if not any(co.offer.offer_type == 'FLASH_SALE' and co.offer.code == d['code'] for co in cart.cartoffer_set.all()) else Decimal('0.00')
            for d in cart.discount_amount
        )
        delivery_fee = cart.delivery_fee
        tax_amount = cart.tax_amount
        print(f'cart_subtotal:{subtotal}')
        # Create the order
        order = Order.objects.create(
            status='CONFIRMED',
            user=user,
            address=address,
            subtotal=subtotal,
            discount_amount=total_discount,  # Store the summed discount
            delivery_fee=delivery_fee,
            tax_amount=tax_amount,
            total_amount=subtotal - total_discount_not_flash  + delivery_fee + tax_amount,
            scheduled_at=scheduled_at,  # Set the scheduled time
        )

        # Transfer offers and update usage
        for cart_offer in cart.cartoffer_set.all():
            offer = cart_offer.offer
            # Find the specific discount amount for this offer from the list
            offer_discount = next(
                (d['amount'] for d in discount_amount_list if d['code'] == offer.code),
                Decimal('0.00')
            )
            OrderOffer.objects.create(
                order=order,
                offer=offer,
                discount_amount=offer_discount  # Use per-offer discount
            )
            if offer_discount > 0 or offer.offer_type in ['BOGO', 'FREE_ITEM']:
                offer.usage_count += 1
                offer.save()
                if cart.user:
                    user_usage, _ = UserOfferUsage.objects.get_or_create(user=cart.user, offer=offer)
                    user_usage.usage_count += 1
                    user_usage.save()

        
        for cart_item in cart.cartitem_set.all():
            print(f'cartitem_subtotal:{cart_item.subtotal}')
            print(f'cartitem_original_subtotal:{cart_item.original_subtotal}')
            
            order_item = OrderItem.objects.create(
                order=order,
                product=cart_item.product,
                deal=cart_item.deal,
                quantity=cart_item.quantity,
                is_free=cart_item.is_free,
                #removable
                unit_sale_price = cart_item.subtotal / Decimal(str(cart_item.quantity)), 
                unit_price=cart_item.original_subtotal / Decimal(str(cart_item.quantity)),  # Average unit price
                subtotal=cart_item.subtotal,
            )
            print(f'orderitem_subtotal:{order_item.subtotal}')
            for customization in cart_item.cartitemcustomization_set.all():
                OrderItemCustomization.objects.create(
                    order_item=order_item,
                    customization_choice=customization.customization_choice,
                    price=customization.price
                )
            for expandable in cart_item.cartitemexpandablechoice_set.all():
                OrderItemExpandableChoice.objects.create(
                    order_item=order_item,
                    expandable_choice=expandable.expandable_choice,
                    price=expandable.price
                )

        cart.cartitem_set.all().delete()
        cart.cartoffer_set.all().delete()
        cart.delete()

        return order

class CarouselScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarouselSchedule
        fields = ['id', 'start_time', 'end_time', 'start_date', 'end_date', 'created_at', 'updated_at',]

class CarouselCardSerializer(serializers.ModelSerializer):
    schedule = CarouselScheduleSerializer(source='carouselschedule', read_only=True)
    
    class Meta:
        model = CarouselCard
        fields = ['id', 'title', 'image', 'description', 'status', 'created_at', 'updated_at', 'schedule','navigate_to']