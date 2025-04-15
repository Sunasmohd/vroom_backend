from datetime import timedelta
from django.utils import timezone
from django.db import models
from django.forms import ValidationError
from decimal import Decimal
from django.core.validators import MinValueValidator, MaxValueValidator
from core.models import User, UserAddress

#? Category is food category like 'Biriyani','Pizza'... and more food drink related only 
#? not 'Best Seller','New','Popular' -- these can be tags as well as computed and given based on sales and ratings
class Category(models.Model):
    title = models.CharField(max_length=100,unique=True)
    image = models.ImageField(upload_to='images/categories/', null=True, blank=True)

    def __str__(self):
        return self.title
    
#? 'Best Seller','New','Popular' -- these can go with tags or computed based on sales and ratings   
class Tags(models.Model):
    title = models.CharField(max_length=100,unique=True)
    # image = models.TextField()
    
    def __str__(self):
        return self.title
    
    
  
  
class Product(models.Model):
    title = models.CharField(max_length=100)
    image = models.ImageField(upload_to='images/products/', null=True, blank=True)
    category = models.ForeignKey(Category,on_delete=models.CASCADE)
    description = models.TextField()
    is_veg = models.BooleanField(default=False)
    price = models.DecimalField(decimal_places=2,max_digits=8)
    is_customizable = models.BooleanField(default=False)
    flash_sale_discount = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    flash_sale_is_percentage = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def flash_sale_price(self):
        """Calculate flash sale price if eligible, respecting applicable_products."""
        active_flash_sale = Offer.get_active_flash_sale()
        if not active_flash_sale:
            return None

        # Stricter eligibility check
        if active_flash_sale.applicable_products.exists():
            # If applicable_products is set, only those products are eligible
            if self not in active_flash_sale.applicable_products.all():
                return None
            # Apply product-level discount if available
            if self.flash_sale_discount is not None:
                if self.flash_sale_is_percentage:
                    discount = self.price * (self.flash_sale_discount / Decimal('100'))
                else:
                    discount = self.flash_sale_discount
                return max(self.price - discount, Decimal('0.00'))
            # Fallback to offer-level discount
            elif active_flash_sale.discount_value is not None:
                if active_flash_sale.is_percentage:
                    discount = self.price * (active_flash_sale.discount_value / Decimal('100'))
                else:
                    discount = active_flash_sale.discount_value
                return max(self.price - discount, Decimal('0.00'))
        else:
            # No applicable_products: only apply to items with flash_sale_discount
            if self.flash_sale_discount is not None:
                if self.flash_sale_is_percentage:
                    discount = self.price * (self.flash_sale_discount / Decimal('100'))
                else:
                    discount = self.flash_sale_discount
                return max(self.price - discount, Decimal('0.00'))
        return None

    @property
    def has_flash_sale(self):
        return self.flash_sale_price is not None
    
    @property
    def is_best_seller(self):
        """Computed: Top 10% of products by sales in the last 30 days."""
        if ProductTags.objects.filter(product=self, tag__title='Best Seller').exists():
            return True  # Manual override
        thirty_days_ago = timezone.now() - timedelta(days=30)
        sales = OrderItem.objects.filter(
            product=self,
            order__created_at__gte=thirty_days_ago,
            order__status__in=['CONFIRMED', 'PREPARING', 'DISPATCHED', 'DELIVERED']
        ).aggregate(total=models.Sum('quantity'))['total'] or 0
        all_products = Product.objects.annotate(
            sales=models.Sum('orderitem__quantity', filter=models.Q(
                orderitem__order__created_at__gte=thirty_days_ago,
                orderitem__order__status__in=['CONFIRMED', 'PREPARING', 'DISPATCHED', 'DELIVERED']
            ))
        ).order_by('-sales')
        threshold = max(1, int(all_products.count() * 0.1))  # Top 10%
        top_sellers = all_products[:threshold]
        return self in [p for p in top_sellers if p.sales]

    @property
    def is_new(self):
        """Computed: Created within the last 7 days."""
        if ProductTags.objects.filter(product=self, tag__title='New').exists():
            return True  # Manual override
        seven_days_ago = timezone.now() - timedelta(days=7)
        # Assuming you add a `created_at` field to Product
        return hasattr(self, 'created_at') and self.created_at >= seven_days_ago

    @property
    def is_popular(self):
        """Computed: Top 20% by sales or manual tag."""
        if ProductTags.objects.filter(product=self, tag__title='Popular').exists():
            return True  # Manual override
        thirty_days_ago = timezone.now() - timedelta(days=30)
        sales = OrderItem.objects.filter(
            product=self,
            order__created_at__gte=thirty_days_ago,
            order__status__in=['CONFIRMED', 'PREPARING', 'DISPATCHED', 'DELIVERED']
        ).aggregate(total=models.Sum('quantity'))['total'] or 0
        all_products = Product.objects.annotate(
            sales=models.Sum('orderitem__quantity', filter=models.Q(
                orderitem__order__created_at__gte=thirty_days_ago,
                orderitem__order__status__in=['CONFIRMED', 'PREPARING', 'DISPATCHED', 'DELIVERED']
            ))
        ).order_by('-sales')
        threshold = max(1, int(all_products.count() * 0.2))  # Top 20%
        top_popular = all_products[:threshold]
        return self in [p for p in top_popular if p.sales]
    
    def __str__(self):
        return f'{self.title} - {self.price}'
    
    
class ProductTags(models.Model):
    product = models.ForeignKey(Product,on_delete=models.CASCADE)
    tag = models.ForeignKey(Tags,on_delete=models.CASCADE)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['product', 'tag'], 
                                    name='product_and_tag_uniq')
        ]
 
class Deal(models.Model):
    title = models.CharField(max_length=100,unique=True)
    description = models.TextField()
    price = models.DecimalField(decimal_places=2,max_digits=7)
    is_expandable = models.BooleanField(default=False) #? checking whether can it add more products to this deal
    is_active = models.BooleanField(default=True)
    image = models.ImageField(upload_to='images/deals/', null=True, blank=True)  # Store in media/images/deals/
    category = models.ManyToManyField(to=Category)
    flash_sale_discount = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    flash_sale_is_percentage = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True,)

    @property
    def flash_sale_price(self):
        """Calculate flash sale price if eligible, respecting applicable_deals."""
        active_flash_sale = Offer.get_active_flash_sale()
        if not active_flash_sale:
            return None

        # Stricter eligibility check
        if active_flash_sale.applicable_deals.exists():
            # If applicable_deals is set, only those deals are eligible
            if self not in active_flash_sale.applicable_deals.all():
                return None
            # Apply deal-level discount if available
            if self.flash_sale_discount is not None:
                if self.flash_sale_is_percentage:
                    discount = self.price * (self.flash_sale_discount / Decimal('100'))
                else:
                    discount = self.flash_sale_discount
                return max(self.price - discount, Decimal('0.00'))
            # Fallback to offer-level discount
            elif active_flash_sale.discount_value is not None:
                if active_flash_sale.is_percentage:
                    discount = self.price * (active_flash_sale.discount_value / Decimal('100'))
                else:
                    discount = active_flash_sale.discount_value
                return max(self.price - discount, Decimal('0.00'))
        else:
            # No applicable_deals: only apply to items with flash_sale_discount
            if self.flash_sale_discount is not None:
                if self.flash_sale_is_percentage:
                    discount = self.price * (self.flash_sale_discount / Decimal('100'))
                else:
                    discount = self.flash_sale_discount
                return max(self.price - discount, Decimal('0.00'))
        return None

    @property
    def has_flash_sale(self):
        return self.flash_sale_price is not None
    
    @property
    def is_best_seller(self):
        if DealTags.objects.filter(deal=self, tag__title='Best Seller').exists():
            return True
        thirty_days_ago = timezone.now() - timedelta(days=30)
        sales = OrderItem.objects.filter(
            deal=self,
            order__created_at__gte=thirty_days_ago,
            order__status__in=['CONFIRMED', 'PREPARING', 'DISPATCHED', 'DELIVERED']
        ).aggregate(total=models.Sum('quantity'))['total'] or 0
        all_deals = Deal.objects.annotate(
            sales=models.Sum('orderitem__quantity', filter=models.Q(
                orderitem__order__created_at__gte=thirty_days_ago,
                orderitem__order__status__in=['CONFIRMED', 'PREPARING', 'DISPATCHED', 'DELIVERED']
            ))
        ).order_by('-sales')
        threshold = max(1, int(all_deals.count() * 0.1))
        top_sellers = all_deals[:threshold]
        return self in [d for d in top_sellers if d.sales]

    @property
    def is_new(self):
        if DealTags.objects.filter(deal=self, tag__title='New').exists():
            return True
        seven_days_ago = timezone.now() - timedelta(days=7)
        # Assuming you add a `created_at` field to Deal
        return hasattr(self, 'created_at') and self.created_at >= seven_days_ago

    @property
    def is_popular(self):
        if DealTags.objects.filter(deal=self, tag__title='Popular').exists():
            return True
        thirty_days_ago = timezone.now() - timedelta(days=30)
        sales = OrderItem.objects.filter(
            deal=self,
            order__created_at__gte=thirty_days_ago,
            order__status__in=['CONFIRMED', 'PREPARING', 'DISPATCHED', 'DELIVERED']
        ).aggregate(total=models.Sum('quantity'))['total'] or 0
        all_deals = Deal.objects.annotate(
            sales=models.Sum('orderitem__quantity', filter=models.Q(
                orderitem__order__created_at__gte=thirty_days_ago,
                orderitem__order__status__in=['CONFIRMED', 'PREPARING', 'DISPATCHED', 'DELIVERED']
            ))
        ).order_by('-sales')
        threshold = max(1, int(all_deals.count() * 0.2))
        top_popular = all_deals[:threshold]
        return self in [d for d in top_popular if d.sales]
    
    def __str__(self):
        return self.title
    
   
class DealTags(models.Model):
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tags, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['deal', 'tag'], name='deal_and_tag_uniq')
        ]

    def __str__(self):
        return f"{self.deal.title} - {self.tag.title}"
     
class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites')
    product = models.ForeignKey('Product', on_delete=models.CASCADE, null=True, blank=True)
    deal = models.ForeignKey('Deal', on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'product'], name='unique_user_product_favorite', condition=models.Q(product__isnull=False)),
            models.UniqueConstraint(fields=['user', 'deal'], name='unique_user_deal_favorite', condition=models.Q(deal__isnull=False)),
        ]

    def clean(self):
        if self.product and self.deal:
            raise ValidationError("Only one of product or deal can be set.")
        if not self.product and not self.deal:
            raise ValidationError("At least one of product or deal must be set.")

    def __str__(self):
        item = self.product.title if self.product else self.deal.title
        return f"{self.user.name} - {item}"
    
class DealProduct(models.Model):
    deal = models.ForeignKey(to=Deal,on_delete=models.CASCADE, related_name='dealproduct_set')
    product = models.ForeignKey(to=Product,on_delete=models.CASCADE)
    
    # class Meta:
    #     constraints = [
    #         models.UniqueConstraint(fields=['product', 'deal'], 
    #                                 name='product_and_deal_uniq')
    #     ]
    def __str__(self):
        return f'{self.deal.title} - {self.product.title}'

class ExpandableHeader(models.Model):
    title = models.CharField(max_length=100)
    
    def __str__(self):
        return self.title  
    
class ExpandableChoices(models.Model):
    #? deal and product can be present if it is related to a deal product expand, only product will be present
    #? means deal = NULL when Make it a meal of a single product is need to be shown
    deal = models.ForeignKey(to=Deal,on_delete=models.CASCADE, null=True,blank=True)
    is_deal_global = models.BooleanField(default=False)
    #? product: The product being offered as an option (e.g., Pizza B, Fries A, Coke A)
    product = models.ForeignKey(to=Product, on_delete=models.CASCADE, null=True, blank=True, related_name='expandable_options')
    #? base_product: The product this option is connected to (e.g., Pizza A)
    base_product = models.ForeignKey(to=Product, on_delete=models.CASCADE, null=True, blank=True, related_name='expandable_choices')
    category = models.ForeignKey(to=Category, on_delete=models.CASCADE, null=True, blank=True)
    expandable_header = models.ForeignKey(ExpandableHeader,on_delete=models.CASCADE)
    #? if need more detail we will add -> product_name save upto 20% -- like this, if nothing leave it blank it will get from the product
    title = models.CharField(max_length=100, null=True,blank=True)
    is_veg = models.BooleanField(default=False)
    price = models.DecimalField(decimal_places=2,max_digits=8) #? if any difference from original amount
    
    def __str__(self):
        return self.title  
    
    def clean(self):
        if self.deal is None and not self.is_deal_global:
            if self.base_product is None and self.category is None:
                raise ValidationError("Either BASE_PRODUCT or CATEGORY must be set if for PRODUCTS, for DEALS Either DEAL or IS_DEAL_GLOBAL must be set")
            elif self.base_product is not None and self.category is not None:
                raise ValidationError("Only one of BASE_PRODUCT or CATEGORY can be set.")
        elif self.deal is not None and self.is_deal_global:
            raise ValidationError("If DEAL has value, can't set IS_DEAL_GLOBAL to True.")
        elif self.deal is not None or self.is_deal_global:
            if not self.base_product is None or not self.category is None:
                raise ValidationError("Can't set BASE_PRODUCT and CATEGORY if deal related DEAL has value or IS_DEAL_GLOBAL=True is set")
    
#? sauces, addons, size, base, toppings, extra cheese
#? max selection can set to null if it can select all
class CustomizationHeader(models.Model):
    title = models.CharField(max_length=100)
    max_selection = models.SmallIntegerField(default=1, null=True, blank=True) #? based on this we set if its a radio button max 1 or check box more than 1
    is_required = models.BooleanField(default=False) #? should select alteast one or any one
     #? there is a chance of multiple name repeat, like base for both burger and pizza, so make both base will make confusion
     #? if we don't have anything to seperate the both bases -- like just base it will be -- but base with subtitle (for burger)
     #? will help admin understand its for burger, so they can add that instead of the confusing base
    subtitle = models.CharField(max_length=100, null=True,blank=True)
    # image = models.TextField()
   
    
    def __str__(self):
        return self.title  
     
     
#? pan, medium, tomato
class CustomizationChoice(models.Model):
    customization_header = models.ForeignKey(CustomizationHeader,on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    is_veg = models.BooleanField(default=False)
    price = models.DecimalField(decimal_places=2,max_digits=8)
    
    def __str__(self):
        return self.title  


#? connecting product like // A Pizza to A Size // sauces, addons, size, base, toppings, extra cheese
class ProductCustomizationHeader(models.Model):
    customization_header = models.ForeignKey(CustomizationHeader,on_delete=models.CASCADE)
    product = models.ForeignKey(to=Product,on_delete=models.CASCADE)
    sort_order = models.SmallIntegerField()
    max_discount = models.DecimalField(decimal_places=2, max_digits=5, null=True, blank=True)  # e.g., 20
    is_percentage = models.BooleanField(default=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['customization_header', 'product'], 
                                    name='customization_header_and_product_uniq')
        ]
        
    def clean(self):
        if self.customization_header.is_required is True and self.max_discount is not None:
            raise ValidationError('for a required header you can\'t set a max discount \
                                  because the chances are it will be a preselected option of\
                                  a product and a product price should match combined preselected options \
                                  so giving it a max discount may lead to mismatch of both prices making it a very bad UX')
            
    def __str__(self):
        return f'{self.product} - {self.customization_header}'

#? This is for price changes based on different choice selections
#? Ex :- Pan in BASE ->  Personal 199, Medium 299 | Stuffed Crust -> Personal 249, Medium 399
#? what happens here is how records will looka like 
#? -> id=1, product='Pizza A', customization_choice='Pan', customization_price_rules_self=NULL, price=0
#? -> id=2, product='Pizza A', customization_choice='Personal', customization_price_rules_self=1, price=199
#? -> id=3, product='Pizza A', customization_choice='Medium', customization_price_rules_self=1, price=299
#? -> id=4, product='Pizza A', customization_choice='Stuffed Crust', customization_price_rules_self=NULL, price=0
#? -> id=5, product='Pizza A', customization_choice='Personal', customization_price_rules_self=4, price=249
#? -> id=6, product='Pizza A', customization_choice='Medium', customization_price_rules_self=4, price=399
#? -> id=7, product='Pizza A', customization_choice='Tomato Sauce', customization_price_rules_self=2, price=50

#? So the takeaway is any customization_choice can be priced or shown based on another choices
#? like 
#? 'Personal' also they can be not connected means standalone like 'Pan' here
class CustomizationPriceRule(models.Model):
    product = models.ForeignKey(to=Product,on_delete=models.CASCADE)
    customization_choice = models.ForeignKey(to=CustomizationChoice,on_delete=models.CASCADE)
    customization_price_rules_self = models.ForeignKey('self', on_delete=models.CASCADE, null=True,blank=True,  #? Allows root categories without parents
        related_name='subpricerules')
    
    #? This price is something that changes for different connections
    price = models.DecimalField(decimal_places=2,max_digits=8)
    is_base = models.BooleanField(default=False)  # New field: marks this rule as base price
    
    def __str__(self):
        if self.customization_price_rules_self != None:
            return f'{self.product.id} - {self.product} - {self.customization_choice.title} - |{self.customization_price_rules_self.customization_choice.title} - {self.customization_price_rules_self.product}| - {self.price}'
        return f'{self.product.id} - {self.product} - {self.customization_choice.title} - |{self.customization_price_rules_self}| - {self.price}'

#? this is where we store if a choice is unavailable not like out of stock
#? we created this table because for some products we have similar customization_choices
#? like a 10 choices will repeat for 50 burgers but sometimes there might be slight
#? changes like only 8 is allowed for some, so what we are trying to do here is we are
#? gonna store the choices only one time in the choices main table, if any pricing difference
#? needed for a specific type of burger we will add that choice in the customizationpricerule
#? table but if like i said if there is only 8 choices for one burger we need to set like
#? if this is the burger user viewing make sure that we omit the 2 burgers from their detailed
#? view, so what we saved here is we avoided unnecessary repetition of combinations like
#? if there is 100 burgers and 20 addons that is 100*20 = 2000 -- in this case if some burgers
#? didn't have a type of choice, we can just make it unavailable, like a max 50 records will be
#? added here, so basically we are cutting down 1950 records and there might be some other cases
#? where other products that has similar cases like a pizza, wrap, so the record might go upto millions
#? which is completely redundant, so what we achieve here we reduce the load of a specific
#? table and the joining is just with one table which only will have less than 1000 records totally
class ProductChoicesUnavailablility(models.Model):
    product = models.ForeignKey(to=Product,on_delete=models.CASCADE)
    customization_choice = models.ForeignKey(to=CustomizationChoice,on_delete=models.CASCADE)
    
    def __str__(self):
        return f'{self.product} - {self.customization_choice}'



#? MENU SECTION -- These two tables manage the main menu, it can be something like a best seller,
                #? drinks, foods, combo deals @999, biriyani anything
class Menu(models.Model):
    title = models.CharField(max_length=100,unique=True)
    # image = models.TextField()
    
    def __str__(self):
        return f'{self.title}'
    
    
class MenuItem(models.Model):
    menu = models.ForeignKey(to=Menu,on_delete=models.CASCADE, related_name='menuitem_set')
    
    #? One of these fields should be null in a record, this is because we don't need
    #? products for deal in this section because in this section we only show basic details
    #? only after the tap we need to show the products associated with it
    product = models.ForeignKey(to=Product,on_delete=models.CASCADE, null=True, blank=True)
    deal = models.ForeignKey(to=Deal,on_delete=models.CASCADE, null=True, blank=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['deal', 'menu'], 
                                    name='menu_and_deal_uniq'),
            models.UniqueConstraint(fields=['product', 'menu'], 
                                    name='product_and_menu_uniq')
        ]
        
    def clean(self):
        if self.product and self.deal:
            raise ValidationError('Product and deal can\'t have value in the same record')
        
    def __str__(self):
        return f'{self.menu.title} {self.product.title if self.product else self.deal.title}'


class Branch(models.Model):
    name = models.CharField(max_length=100)  # e.g., "McDonald's Downtown"
    address = models.TextField()
    city = models.CharField(max_length=100,)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=15, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    opening_time = models.TimeField(null=True, blank=True)
    closing_time = models.TimeField(null=True, blank=True)
    delivery_radius = models.DecimalField(max_digits=5, decimal_places=2, default=5.00)
    min_order_amount = models.DecimalField(max_digits=8, decimal_places=2, default=10.00)
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=5.00)

    def __str__(self):
        return f"{self.name} - {self.city}"

    def is_open(self):
        if not (self.opening_time and self.closing_time):
            return True
        now = timezone.localtime(timezone.now()).time()
        if self.opening_time <= self.closing_time:
            return self.opening_time <= now <= self.closing_time
        else:  # Overnight hours
            return now >= self.opening_time or now <= self.closing_time

class ProductBranchStock(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    is_available = models.BooleanField(default=True)  # False means not offered at this branch
    is_out_of_stock = models.BooleanField(default=False)  # True means temporarily unavailable
    out_of_stock_from = models.DateTimeField(null=True, blank=True)  # When out-of-stock starts
    out_of_stock_until = models.DateTimeField(null=True, blank=True)  # When it becomes available again
    price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)  # Optional branch-specific price override

    class Meta:
        unique_together = ('branch', 'product')

    def __str__(self):
        return f"{self.product.title} at {self.branch.name}"

    def get_availability_status(self):
        """Determine current status and a dynamic message based on out_of_stock_until."""
        now = timezone.now()

        if not self.is_available:
            return {"status": "unavailable", "message": "Not available at this branch"}

        if self.is_out_of_stock and self.out_of_stock_from and self.out_of_stock_until:
            if self.out_of_stock_from <= now <= self.out_of_stock_until:
                time_diff = self.out_of_stock_until - now
                days_diff = time_diff.days

                if days_diff == 0:  # Today
                    return {
                        "status": "out_of_stock",
                        "message": f"Out of stock, available at {self.out_of_stock_until.strftime('%I:%M %p')}"
                    }
                elif days_diff == 1:  # Tomorrow
                    return {
                        "status": "out_of_stock",
                        "message": f"Out of stock, available at {self.out_of_stock_until.strftime('%I:%M %p tomorrow')}"
                    }
                elif 1 < days_diff <= 7:  # Within a week
                    return {
                        "status": "out_of_stock",
                        "message": f"Out of stock, available {self.out_of_stock_until.strftime('this %A at %I:%M %p')}"
                    }
                else:  # More than a week
                    return {
                        "status": "out_of_stock",
                        "message": f"Out of stock, available on {self.out_of_stock_until.strftime('%B %d, %Y at %I:%M %p')}"
                    }
            elif now < self.out_of_stock_from:  # Out of stock hasn't started yet
                return {"status": "available", "message": "In stock (out of stock soon)"}
            # If now > out_of_stock_until, stock is back

        return {"status": "available", "message": "In stock"}

# Optionally, if you want to handle deals similarly
class DealBranchStock(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE)
    is_available = models.BooleanField(default=True)  # False means not offered at this branch
    is_out_of_stock = models.BooleanField(default=False)  # True means temporarily unavailable
    out_of_stock_from = models.DateTimeField(null=True, blank=True)
    out_of_stock_until = models.DateTimeField(null=True, blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)  # Optional branch-specific price override

    class Meta:
        unique_together = ('branch', 'deal')

    def __str__(self):
        return f"{self.deal.title} at {self.branch.name}"

    def get_availability_status(self):
        return ProductBranchStock.get_availability_status(self)

# Offer Management
class Offer(models.Model):
    OFFER_TYPES = (
        ('PERCENTAGE', 'Percentage Discount'),
        ('FLAT', 'Flat Discount'),
        ('BOGO', 'Buy One Get One'),
        ('FREE_DELIVERY', 'Free Delivery'),
        ('FREE_ITEM', 'Free Item'),  # New type for free product offers
        ('FLASH_SALE', 'Flash Sale'),
    )
    USAGE_SCOPES = (
        ('SINGLE_USER', 'Single User'),  # e.g., voucher for one user
        ('MULTI_USER', 'Multi-User'),    # e.g., shared promo code
        ('UNLIMITED', 'Unlimited'),      # e.g., app-wide offer
    )
    
    code = models.CharField(max_length=20, unique=True)
    offer_type = models.CharField(max_length=20, choices=OFFER_TYPES)
    discount_value = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    min_spend = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    max_discount = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    description = models.TextField()
    auto_apply = models.BooleanField(default=False)
    near_unlock_threshold = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    is_percentage = models.BooleanField(default=False) # this is for flash sale only
    usage_limit = models.PositiveIntegerField(null=True, blank=True)  # Total redemptions allowed
    usage_count = models.PositiveIntegerField(default=0)  # Total redemptions so far
    usage_scope = models.CharField(max_length=20, choices=USAGE_SCOPES, default='UNLIMITED')
    per_user_limit = models.PositiveIntegerField(default=1)  # Max uses per user
    applicable_products = models.ManyToManyField('Product', blank=True, related_name='flash_sale_offers')
    applicable_deals = models.ManyToManyField('Deal', blank=True, related_name='flash_sale_offers')
    free_products = models.ManyToManyField(Product, blank=True, )
    free_deals = models.ManyToManyField(Deal, blank=True, )
    free_item_quantity = models.PositiveIntegerField(default=1, help_text="Number of free items to provide (for FREE_ITEM offers)")
    branch = models.ForeignKey('Branch', on_delete=models.SET_NULL, null=True, blank=True)
    applicable_headers = models.ManyToManyField(ProductCustomizationHeader, blank=True)

    def clean(self):
        if not self.is_percentage and self.applicable_headers.filter(
            customization_header__is_required=True
        ).exists():
            raise ValidationError("Flat discounts are not allowed with required customization headers.")

    def save(self, *args, **kwargs):
        if(self.near_unlock_threshold == None):
            self.near_unlock_threshold = self.min_spend
        if self.offer_type == 'FLASH_SALE':
            self.auto_apply = True
            
        super().save(*args, **kwargs)
        
    @classmethod
    def get_active_flash_sale(cls):
        """Return the active flash sale offer, if any."""
        from django.utils import timezone
        return cls.objects.filter(
            offer_type='FLASH_SALE',
            is_active=True,
            valid_from__lte=timezone.now(),
            valid_until__gte=timezone.now()
        ).first()
        
    def clean(self):
        if self.offer_type in ['PERCENTAGE', 'FLAT'] and self.discount_value is None:
            raise ValidationError(f"Discount value is required for {self.offer_type}.")
        if self.offer_type in ['BOGO', 'FREE_ITEM'] and not (self.free_products or self.free_deals):
            raise ValidationError(f"Free product or deal required for {self.offer_type}.")
        if self.valid_until <= self.valid_from:
            raise ValidationError("valid_until must be after valid_from.")


class UserOfferUsage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE)
    usage_count = models.PositiveIntegerField(default=0)
    last_used = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'offer')
   
    
class Cart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)

    @property
    def delivery_fee(self):
        return self.branch.delivery_fee if self.branch else Decimal('5.00')
    
    @property
    def base_total(self):
        """Total before discounts, including subtotal, delivery fee, and tax."""
        return self.subtotal + self.delivery_fee + self.tax_amount
    
    @property
    def subtotal(self):
        """Sum of all item subtotals before discounts."""
        return sum(item.subtotal or Decimal('0.00') for item in self.cartitem_set.all()) or Decimal('0.00')

    @property
    def tax_amount(self):
        """Tax calculated as a percentage of subtotal after discount."""
        taxable_amount = self.subtotal
        return taxable_amount * Decimal('0.10')  # 10% tax rate; adjust as needed

    @property
    def discount_amount(self):
            """Return a list of discounts with code and amount."""
            discounts = []
            
            # Calculate base values
            current_subtotal = sum(item.subtotal or Decimal('0.00') for item in self.cartitem_set.all()) or Decimal('0.00')
            current_delivery_fee = self.branch.delivery_fee if self.branch else Decimal('5.00')
            current_tax = current_subtotal * Decimal('0.10')
            base_total_value = current_subtotal + current_delivery_fee + current_tax
            
            # Handle FLASH_SALE discount (item-level)
            flash_sale_discount = Decimal('0.00')
            for item in self.cartitem_set.filter(is_free=False):
                original = item.original_subtotal
                discounted = item.subtotal
                if discounted is not None and original > discounted:# Flash sale applied
                    flash_sale_discount += (original - discounted)
            if flash_sale_discount > Decimal('0.00'):
                flash_sale_offer = self.cartoffer_set.filter(offer__offer_type='FLASH_SALE').first()
                if flash_sale_offer:
                    discounts.append({
                        'code': flash_sale_offer.offer.code,
                        'amount': flash_sale_discount
                    })

            # Handle other offers (cart-level)
            applicable_offers = self.cartoffer_set.filter(
                offer__valid_from__lte=timezone.now(),
                offer__valid_until__gte=timezone.now()
            ).exclude(offer__offer_type='FLASH_SALE')  # Exclude FLASH_SALE here
            
            for cart_offer in applicable_offers:
                offer = cart_offer.offer
                if offer.min_spend and base_total_value < offer.min_spend:
                    continue
                discount_amount = Decimal('0.00')
                if offer.offer_type == 'FLAT':
                    discount_amount = min(offer.discount_value, base_total_value)
                elif offer.offer_type == 'PERCENTAGE':
                    potential_discount = base_total_value * (offer.discount_value / Decimal('100'))
                    discount_amount = min(potential_discount, offer.max_discount or Decimal('Infinity'))
                if discount_amount > Decimal('0.00'):
                    discounts.append({
                        'code': offer.code,
                        'amount': discount_amount
                    })
            return discounts
        
    @property
    def total(self):
        """Final total after applying discounts."""
        current_subtotal = sum(item.subtotal or Decimal('0.00') for item in self.cartitem_set.all()) or Decimal('0.00')
        current_delivery_fee = self.branch.delivery_fee if self.branch else Decimal('5.00')
        current_tax = current_subtotal * Decimal('0.10')
        base_total_value = current_subtotal + current_delivery_fee + current_tax
        total_discount = sum(
            d['amount'] if not any(co.offer.offer_type == 'FLASH_SALE' and co.offer.code == d['code'] for co in self.cartoffer_set.all()) else Decimal('0.00')
            for d in self.discount_amount
        )
        return base_total_value - total_discount



class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True)
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    is_free = models.BooleanField(default=False)  # Add this
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))  # Single item OG price
    unit_sale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # Single item sale price
    
    class Meta:
        ordering = ['is_free']
        
    def get_signature(self):
        """Generate a unique signature for this cart item based on product/deal and customizations."""
        item = self.product or self.deal
        item_id = f"{item.__class__.__name__}-{item.id}" if item else "None"
        customization_ids = sorted(
            f"{c.deal_product_id or 'none'}:{c.customization_choice_id}"
            for c in self.cartitemcustomization_set.all()
        )
        expandable_ids = sorted(
            f"{e.deal_product_id or 'none'}:{e.expandable_choice_id}"
            for e in self.cartitemexpandablechoice_set.all()
        )
        return "|".join([
            item_id,
            ":".join(customization_ids),
            ":".join(expandable_ids)
        ])

    def calculate_unit_prices(self, deal_price = None):
        """Calculate unit_price and unit_sale_price for one item, tracing parent-child hierarchy."""
        if self.is_free:
            self.unit_price = Decimal('0.00')
            self.unit_sale_price = Decimal('0.00')
            return

        customizations = self.cartitemcustomization_set.all()

        # Original unit price
        total_original = Decimal('0.00')
        if self.product:
            for c in customizations:
                total_original += c.original_price  # Sums Pan, Personal, Garlic Sauce
            if total_original == 0:
                total_original = self.product.price
        
        if self.deal:
            total_original = Decimal(deal_price)
        
        expandable_total = sum(e.price for e in self.cartitemexpandablechoice_set.all()) or Decimal('0.00')
        self.unit_price = total_original + expandable_total

        # Sale unit price
        if self.product and self.product.has_flash_sale:
            total_sale = Decimal('0.00')
            for c in customizations:
                total_sale += c.price
            if total_sale == 0:
                total_sale = self.product.flash_sale_price
            sale_expandable_total = sum(e.price for e in self.cartitemexpandablechoice_set.all()) or Decimal('0.00')
            self.unit_sale_price = total_sale + sale_expandable_total
        else:
            self.unit_sale_price = None
            
    @property
    def subtotal(self):
        """Total with discounts, only if flash sale applies, else None."""
        if self.is_free:
            return Decimal('0.00')
        # Sum all discounted prices from customizations
        customizations = self.cartitemcustomization_set.all()
        expandable_total = sum(e.price for e in self.cartitemexpandablechoice_set.all()) or Decimal('0.00')
        total = expandable_total
        
        if self.deal:
            total += self.unit_price
            return total * Decimal(str(self.quantity))
        for c in customizations:
            total += c.price  # Use discounted price from frontend
        if self.product and self.product.has_flash_sale and total == 0:
            total += self.product.flash_sale_price
        elif self.product and total == 0:
            total += self.product.price
        
        return total * Decimal(str(self.quantity))

    @property
    def original_subtotal(self):
        """Total with original prices, always computed."""
        if self.is_free:
            return Decimal('0.00')
        customizations = self.cartitemcustomization_set.all()
        expandable_total = sum(e.price for e in self.cartitemexpandablechoice_set.all()) or Decimal('0.00')
        total = expandable_total
        
        if self.deal:
            total += self.unit_price
            return total * Decimal(str(self.quantity))
        for c in customizations:
            total += c.original_price  # Use discounted price from frontend
        if self.product and total == 0:
            total += self.product.price
        
        return total * Decimal(str(self.quantity))
    
class CartItemCustomization(models.Model):
    cart_item = models.ForeignKey(CartItem, on_delete=models.CASCADE)
    customization_choice = models.ForeignKey(CustomizationChoice, on_delete=models.CASCADE)
    deal_product = models.ForeignKey(DealProduct, on_delete=models.CASCADE, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    original_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        indexes = [
            models.Index(fields=['cart_item'], name='idx_cartitemcustomization_cart'),
            models.Index(fields=['customization_choice'], name='idx_cartitemcustom_choice'),
            models.Index(fields=['deal_product'], name='idx_cartitemcustom_dealproduct'),  # Index for performance
        ]
    
    def __str__(self):
        return f"{self.customization_choice.title} at {self.price}" 

class CartItemExpandableChoice(models.Model):
    cart_item = models.ForeignKey(CartItem, on_delete=models.CASCADE)
    expandable_choice = models.ForeignKey(ExpandableChoices, on_delete=models.CASCADE, null=True, blank=True)
    deal_product = models.ForeignKey(DealProduct, on_delete=models.CASCADE, null=True, blank=True)  # New field
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        indexes = [
            models.Index(fields=['cart_item'], name='idx_cartitemexpandable_cart'),
            models.Index(fields=['expandable_choice'], name='idx_cartitemexp_choice'),
            models.Index(fields=['deal_product'], name='idx_cartitemexp_dealproduct'),  # Index for performance
        ]

class CartOffer(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE)
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE)
    applied_by_user = models.BooleanField(default=False)
    
    
class SpecialSuggestionsBranchWise(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True)
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, null=True, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    
    def clean(self):
        if self.product and self.deal:
            raise ValidationError("Only one of it can be added")

    
class Order(models.Model):
    ORDER_STATUS = (
        ('PENDING', 'Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('PREPARING', 'Preparing'),
        ('DISPATCHED', 'Dispatched'),
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
    )
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null = True, blank = True)
    address = models.ForeignKey(UserAddress, on_delete=models.SET_NULL, null = True, blank = True)  # Assume UserAddress exists
    offer = models.ForeignKey(Offer, on_delete=models.SET_NULL, null=True, blank=True)  # Adjusted to 
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='PENDING')
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)  # Before discounts
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # From offer
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)  # Added
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)  # Subtotal - discount + delivery + tax
    payment_status = models.CharField(max_length=20, default='PENDING')  # e.g., PENDING, PAID
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)  # New field for scheduling

    class Meta:
        ordering = ['-id']

    def clean(self):
        if self.scheduled_at and self.scheduled_at <= timezone.now():
            raise ValidationError("Scheduled time must be in the future.")


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True)
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, null=True, blank=True)  # Added
    quantity = models.PositiveSmallIntegerField(default=1)
    unit_sale_price = models.DecimalField(max_digits=8, decimal_places=2, null=True,blank=True)  # Price at order time
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)  # Price at order time
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)  # quantity * unit_price
    is_free = models.BooleanField(default=False)  # Add this

    def save(self, *args, **kwargs):
        # item = self.product or self.deal
        # self.unit_price = item.price if item else 0
        if not self.is_free:
            self.subtotal = self.quantity * self.unit_price
        else:
            self.subtotal = Decimal(0.0)
        super().save(*args, **kwargs)

class OrderItemCustomization(models.Model):
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE)
    customization_choice = models.ForeignKey('CustomizationChoice', on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=8, decimal_places=2)

    # class Meta:
    #     unique_together = ('order_item', 'customization_choice')

class OrderItemExpandableChoice(models.Model):
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE)
    expandable_choice = models.ForeignKey('ExpandableChoices', on_delete=models.CASCADE)  # Adjusted name
    price = models.DecimalField(max_digits=8, decimal_places=2)

    # class Meta:
    #     unique_together = ('order_item', 'expandable_choice')
        
# models.py
class OrderOffer(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('order', 'offer') 
               
           

# Booking Management
class Booking(models.Model):
    BOOKING_STATUS = (
        ('PENDING', 'Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    )
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    booking_date = models.DateTimeField()
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True)
    party_size = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=20, choices=BOOKING_STATUS, default='PENDING')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Booking #{self.id} - {self.user.email} ({self.booking_date})"
    
    def clean(self):
        if self.booking_date <= timezone.now():
            raise ValidationError("Booking date must be in the future.")
        if self.party_size > 20:  # Example max capacity
            raise ValidationError("Party size cannot exceed 20.")

# Invoice Management
class Invoice(models.Model):
    INVOICE_STATUS = (
        ('PENDING', 'Pending'),
        ('PAID', 'Paid'),
        ('FAILED', 'Failed'),
    )
    order = models.OneToOneField(Order, on_delete=models.CASCADE, null=True, blank=True)
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, null=True, blank=True)
    invoice_number = models.CharField(max_length=20, unique=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=INVOICE_STATUS, default='PENDING')
    issued_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def clean(self):
        if (self.order is None and self.booking is None) or (self.order is not None and self.booking is not None):
            raise ValidationError("Exactly one of order or booking must be set.")

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = f"INV-{timezone.now().strftime('%Y%m%d')}-{self.order.id}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.invoice_number

# Cancellation Management
class Cancellation(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, null=True, blank=True)
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, null=True, blank=True)
    reason = models.TextField()
    cancelled_at = models.DateTimeField(auto_now_add=True)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    def clean(self):
        if (self.order is None and self.booking is None) or (self.order is not None and self.booking is not None):
            raise ValidationError("Exactly one of order or booking must be set.")

    def __str__(self):
        return f"Cancellation for Order #{self.order.id}"

# Payment Method Management
class PaymentMethod(models.Model):
    PAYMENT_TYPES = (
        ('credit', 'Credit Card'),
        ('debit', 'Debit Card'),
        ('upi', 'UPI'),
        ('cod', 'Cash on Delivery'),
        ('wallet', 'Wallet'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPES)
    provider = models.CharField(max_length=50, blank=True)  # e.g., Visa, Paytm
    last_four = models.CharField(max_length=4, blank=True)  # For cards
    is_default = models.BooleanField(default=False)
    expiry_month = models.CharField(max_length=2, default=11) # for cards only -- 0 to 11
    expiry_year = models.CharField(max_length=4, default=2025) # for cards only
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'payment_type', 'last_four','expiry_year','expiry_month')

    def __str__(self):
        return f"{self.user.email} - {self.payment_type} ({self.last_four})"

class Transaction(models.Model):
    TRANSACTION_STATUS = (
        ('PENDING', 'Pending'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
    )
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, null=True, blank=True)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, null=True, blank=True)
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.SET_NULL,null = True, blank = True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=TRANSACTION_STATUS, default='PENDING')
    transaction_id = models.CharField(max_length=100, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def clean(self):
        if sum(1 for x in [self.invoice, self.order, self.booking] if x is not None) != 1:
            raise ValidationError("Exactly one of invoice, order, or booking must be set.")

    def __str__(self):
        if self.invoice != None:
            return f"Transaction {self.transaction_id} - {self.invoice.invoice_number}"
        else:
            return f"Transaction {self.transaction_id} - {self.invoice}"

# Delivery Management
class DeliveryAgent(models.Model):
    name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=15, unique=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Delivery(models.Model):
    DELIVERY_STATUS = (
        ('ASSIGNED', 'Assigned'),
        ('PICKED_UP', 'Picked Up'),
        ('IN_TRANSIT', 'In Transit'),
        ('DELIVERED', 'Delivered'),
        ('FAILED', 'Failed'),
    )
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    agent = models.ForeignKey(DeliveryAgent, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=DELIVERY_STATUS, default='ASSIGNED')
    assigned_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    tracking_url = models.URLField(blank=True)

    def __str__(self):
        return f"Delivery for Order #{self.order.id}"

# Review and Rating
class Review(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, null=True, blank=True)
    rating = models.PositiveSmallIntegerField()  # 1-5
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product', 'order')

    def clean(self):
        if (self.product is None and self.order is None) or (self.product is not None and self.order is not None):
            raise ValidationError("Exactly one of product or order must be set.")
        if self.rating < 1 or self.rating > 5:
            raise ValidationError("Rating must be between 1 and 5.")

    def __str__(self):
        return f"Review by {self.user.email} - Rating: {self.rating}"
    
    
class CarouselCard(models.Model):
    STATUS_CHOICES = [
        ('draft','Draft'),
        ('published','Published'),
    ]
    
    title = models.CharField(max_length=255)
    image = models.ImageField(upload_to='images/carousel/', null=True, blank=True)
    description = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    sort_order =models.IntegerField(default=0)
    navigate_to = models.CharField(max_length=50, default='offer_screen_page') # if page name is OfferScreenPage -- save as offer_screen_page
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['sort_order']


class CarouselSchedule(models.Model):
    carousel_card = models.OneToOneField(CarouselCard,on_delete=models.CASCADE)
    start_time = models.TimeField(null=True,blank=True)
    end_time = models.TimeField(null=True,blank=True)
    # day_of_week = models.PositiveSmallIntegerField(max_length=1,validators=[MinValueValidator(0), MaxValueValidator(6)])
    start_date = models.DateField(null=True,blank=True)
    end_date = models.DateField(null=True,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def clean(self):
        """
        Custom validation for start_date, end_date, start_time, and end_time.
        """
        # Rule 1: start_date cannot be greater than end_date
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError("Start date cannot be greater than end date.")

        # If both dates are provided
        if self.start_date and self.end_date:
            # Rule 2: If start_date equals end_date, start_time must be less than end_time
            if self.start_date == self.end_date:
                if self.start_time and self.end_time and self.start_time >= self.end_time:
                    raise ValidationError("When start date equals end date, start time must be less than end time.")
            # If dates are different, no restriction on start_time vs end_time (e.g., March 12 11 PM to March 13 1 AM is valid)

        # If no dates are provided (both null)
        if not self.start_date and not self.end_date:
            if self.start_time and self.end_time and self.start_time >= self.end_time:
                raise ValidationError("When no dates are provided, start time must be less than end time.")

        # Ensure at least one field is provided to avoid meaningless schedules
        if not self.start_date and not self.end_date and not self.start_time and not self.end_time:
            raise ValidationError("At least one of start_date, end_date, start_time, or end_time must be provided.")

    def save(self, *args, **kwargs):
        # Run validation before saving
        self.full_clean()  # This calls clean() and other built-in validations
        super().save(*args, **kwargs)