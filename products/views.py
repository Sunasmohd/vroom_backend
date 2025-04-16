from datetime import datetime
from core.models import User
from core.views import decode_jwt
from .serializers import *
from .models import *
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from django.utils import timezone
import stripe
from vroom_backend import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from django.db import models
from django.core.cache import cache
from django.db import transaction
import os
from django.db import close_old_connections
from dotenv import load_dotenv

load_dotenv()

stripe.api_key = os.environ.get('STRIPE_API_KEY')

@api_view(['GET'])
def category_list_view(request):
    try:
        categories = Category.objects.all()
        
        serializer = CategorySerializer(
            categories,
            many=True,
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        print(f"Error in category_list_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
def product_list_view(request):
    try:
        products = Product.objects.all()

        # Optional filtering by category
        category_id = request.query_params.get('category_id', None)
        if category_id:
            products = products.filter(category=category_id)

        # Get multiple branch_ids from query parameters
        branch_ids = request.query_params.getlist('branch_id')
        
        if branch_ids:
                # Get all product IDs in the current queryset
                product_ids = products.values_list('id', flat=True)

                # Fetch stock records for these products and branches
                stock_records = ProductBranchStock.objects.filter(
                    branch_id__in=branch_ids,
                    product_id__in=product_ids
                ).values('product_id', 'branch_id', 'is_available')

                # Group by product to determine availability
                product_availability = {}
                for product_id in product_ids:
                    product_stocks = [r for r in stock_records if r['product_id'] == product_id]
                    total_branches_with_stock = len(product_stocks)
                    unavailable_branches = sum(1 for stock in product_stocks if not stock['is_available'])

                    # Product is unavailable only if it's unavailable at all branches
                    if total_branches_with_stock == len(branch_ids) and unavailable_branches == len(branch_ids):
                        product_availability[product_id] = False
                    else:
                        product_availability[product_id] = True

                # Filter out products unavailable at all branches
                unavailable_product_ids = [pid for pid, available in product_availability.items() if not available]
                products = products.exclude(id__in=unavailable_product_ids)
                
        # Pass branch_ids to serializer context
        serializer = ProductDetailSerializer(
            products,
            many=True,
            context={'branch_ids': branch_ids if branch_ids else None}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
    except ValueError as ve:
        return Response({'error': 'Invalid branch_id format'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        print(f"Error in product_list_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
@api_view(['GET'])
def product_detail_view(request, product_id):
    try:
        product = Product.objects.get(id=product_id)

        # Get multiple branch_ids from query parameters
        branch_ids = request.query_params.getlist('branch_id')
        

        # Pass branch_ids to serializer context
        serializer = ProductDetailSerializer(
            product,
            context={'branch_ids': branch_ids if branch_ids else None}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Product.DoesNotExist:
        return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as ve:
        return Response({'error': 'Invalid branch_id format'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        print(f"Error in product_detail_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    

@api_view(['GET'])
def menu_list_view(request):
    try:
        # Get multiple branch_ids from query parameters
        branch_ids = request.query_params.getlist('branch_id')
        menus = Menu.objects.prefetch_related('menuitem_set__product', 'menuitem_set__deal').all()
        
        # Optional filtering by title
        title = request.query_params.get('title', None)
        if title:
            menus = menus.filter(title__icontains=title)
        
        # Pass branch_ids to serializer context for filtering items
        serializer = MenuSerializer(menus, many=True, context={'branch_ids': branch_ids if branch_ids else None})
        
        # Filter out menus with no items
        filtered_data = [menu_data for menu_data in serializer.data if menu_data['items']]
        
        # Return response only if there are menus with items, otherwise return empty list
        return Response(filtered_data, status=status.HTTP_200_OK)
    
    except ValueError as ve:
        return Response({'error':str(ve)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        print(f"Error in menu_list_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    finally:
         close_old_connections()

@api_view(['POST'])
def deal_create_view(request):
    try:
        serializer = DealCreationSerializer(data=request.data)
        if serializer.is_valid():
            deal = serializer.save()
            output_serializer = DealSerializer(deal)
            return Response(output_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        print(f"Error in deal_create_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    

@api_view(['GET'])
def special_suggestions_list_view(request):
    """
    List special suggestions, filtered by branch_ids, excluding items unavailable at all branches.
    """
    try:
        # Get list of branch_ids from query parameters
        branch_ids = request.query_params.getlist('branch_id')
        if not branch_ids:
            return Response({'error': 'At least one branch_id must be provided'}, status=status.HTTP_400_BAD_REQUEST)

        # Convert branch_ids to integers, filtering out invalid entries
        branch_ids = [int(bid) for bid in branch_ids if bid.isdigit()]
        if not branch_ids:
            return Response({'error': 'Invalid branch_id format'}, status=status.HTTP_400_BAD_REQUEST)

        # Fetch all special suggestions with related product and deal data
        suggestions = SpecialSuggestionsBranchWise.objects.select_related('product', 'deal', 'branch').filter(branch_id__in=branch_ids)

        # Get unique product and deal IDs from suggestions
        product_ids = suggestions.filter(product__isnull=False).values_list('product_id', flat=True).distinct()
        deal_ids = suggestions.filter(deal__isnull=False).values_list('deal_id', flat=True).distinct()

        # Fetch stock records for products and deals across the specified branches
        product_stocks = ProductBranchStock.objects.filter(
            branch_id__in=branch_ids,
            product_id__in=product_ids
        ).values('product_id', 'branch_id', 'is_available')

        # For deals, assume availability is tied to their products (adjust if Deal has its own stock model)
        deal_product_stocks = ProductBranchStock.objects.filter(
            branch_id__in=branch_ids,
            product__dealproduct__deal_id__in=deal_ids
        ).values('product_id', 'branch_id', 'is_available')

        # Determine availability for products
        product_availability = {}
        for product_id in product_ids:
            stocks = [s for s in product_stocks if s['product_id'] == product_id]
            total_branches_with_stock = len(stocks)
            unavailable_branches = sum(1 for s in stocks if not s['is_available'])

            # Product is unavailable if it's out of stock at all branches
            if total_branches_with_stock == len(branch_ids) and unavailable_branches == len(branch_ids):
                product_availability[product_id] = False
            else:
                product_availability[product_id] = True

        # Determine availability for deals (based on their products)
        deal_availability = {}
        for deal_id in deal_ids:
            # Get all product stocks related to this deal
            deal_products = Product.objects.filter(dealproduct__deal_id=deal_id).values_list('id', flat=True)
            deal_stocks = [s for s in deal_product_stocks if s['product_id'] in deal_products]
            total_branches_with_stock = len(set(s['branch_id'] for s in deal_stocks))
            unavailable_branches = sum(1 for s in deal_stocks if not s['is_available'])

            # Deal is unavailable if all its products are unavailable at all branches
            if total_branches_with_stock == len(branch_ids) and unavailable_branches == len(deal_stocks):
                deal_availability[deal_id] = False
            else:
                deal_availability[deal_id] = True

        # Filter suggestions to exclude unavailable products and deals
        filtered_suggestions = []
        seen_products = set()
        seen_deals = set()

        for suggestion in suggestions:
            if suggestion.product:
                if suggestion.product_id in seen_products or not product_availability.get(suggestion.product_id, True):
                    continue
                seen_products.add(suggestion.product_id)
                filtered_suggestions.append(suggestion)
            elif suggestion.deal:
                if suggestion.deal_id in seen_deals or not deal_availability.get(suggestion.deal_id, True):
                    continue
                seen_deals.add(suggestion.deal_id)
                filtered_suggestions.append(suggestion)

        # Serialize the filtered suggestions
        serializer = SpecialSuggestionsBranchWiseSerializer(
            filtered_suggestions,
            many=True,
            context={'branch_ids': branch_ids}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    except ValueError as ve:
        return Response({'error': 'Invalid branch_id format'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        print(f"Error in special_suggestions_list_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    finally:
            close_old_connections()

@api_view(['GET'])
def deal_list_view(request):
    try:
        deals = Deal.objects.prefetch_related('dealproduct_set__product').all()
        
        category_id = request.query_params.get('category_id', None)
        if category_id:
            deals = deals.filter(category=category_id)
            
            
            
        
        
        # Get multiple branch_ids from query parameters
        branch_ids = request.query_params.getlist('branch_id')
        if branch_ids:
            branch_ids = [int(bid) for bid in branch_ids if bid.isdigit()]

        serializer = DealSerializer(
            deals,
            many=True,
            context={'branch_ids': branch_ids if branch_ids else None}
        )
        
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        print(f"Error in deal_list_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def deal_detail_view(request, deal_id):
    try:
        # Fetch the specific deal by ID
        deal = Deal.objects.prefetch_related('dealproduct_set__product').get(id=deal_id)
        # Get multiple branch_ids from query parameters
        branch_ids = request.query_params.getlist('branch_id')
        if branch_ids:
            branch_ids = [int(bid) for bid in branch_ids if bid.isdigit()]
        serializer = DealSerializer(
            deal,
            many=False,
            context={'branch_ids': branch_ids if branch_ids else None}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Deal.DoesNotExist:
        return Response({'error': f'Deal with id {deal_id} not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f"Error in deal_detail_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
# @api_view(['GET'])
# def favorite_list_view(request):
#     """
#     List all favorites for the authenticated user.
#     """
#     try:
#         favorites = Favorite.objects.filter(user=request.user)
#         serializer = FavoriteSerializer(favorites, many=True, context={'request': request})
#         return Response(serializer.data, status=status.HTTP_200_OK)
#     except Exception as e:
#         print(f"Error in favorite_list_view: {e}")
#         return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
#     finally:
#          close_old_connections()

# @api_view(['POST'])
# def favorite_create_view(request):
#     """
#     Create a new favorite for the authenticated user.
#     """
#     try:
#         serializer = FavoriteSerializer(data=request.data, context={'request': request})
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data, status=status.HTTP_201_CREATED)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
#     except Exception as e:
#         print(f"Error in favorite_create_view: {e}")
#         return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

# @api_view(['DELETE'])
# def favorite_delete_view(request, favorite_id):
#     """
#     Delete a favorite by ID.
#     """
#     try:
#         favorite = Favorite.objects.get(id=favorite_id, user=request.user)
#         favorite.delete()
#         return Response(status=status.HTTP_204_NO_CONTENT)
#     except Favorite.DoesNotExist:
#         return Response({'error': 'Favorite not found'}, status=status.HTTP_404_NOT_FOUND)
#     except Exception as e:
#         print(f"Error in favorite_delete_view: {e}")
#         return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def favorite_list_view(request):
    """
    List all favorites. For non-logged-in users, use query params; for logged-in, use user ID.
    """
    try:
        if request.user.is_authenticated:
            favorites = Favorite.objects.filter(user=request.user)
        else:
            product_ids = request.query_params.get('product_ids', '').split(',')
            deal_ids = request.query_params.get('deal_ids', '').split(',')
            product_ids = [pid for pid in product_ids if pid.isdigit()]
            deal_ids = [did for did in deal_ids if did.isdigit()]
            favorites = Favorite.objects.filter(
                product__id__in=product_ids, user__isnull=True
            ) | Favorite.objects.filter(deal__id__in=deal_ids, user__isnull=True)
        
        serializer = FavoriteSerializer(favorites, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        print(f"Error in favorite_list_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    finally:
        close_old_connections()

@api_view(['POST'])
def favorite_create_view(request):
    """
    Create a new favorite. For non-logged-in users, store locally; for logged-in, save to DB.
    """
    try:
        data = request.data.copy()
        print(request.user.is_authenticated)
        if request.user.is_authenticated:
            data['user'] = request.user.id
        else:
            data['user'] = None  # Non-logged-in favorites can be stored with null user
            print(data['user'])
            
        serializer = FavoriteSerializer(data=data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        print(f"Error in favorite_create_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['DELETE'])
def favorite_delete_view(request, favorite_id):
    """
    Delete a favorite by ID. For non-logged-in users, rely on client-side logic.
    """
    try:
        if request.user.is_authenticated:
            favorite = Favorite.objects.get(id=favorite_id, user=request.user)
        else:
            favorite = Favorite.objects.get(id=favorite_id)
        favorite.delete()
        
        return Response(status=status.HTTP_204_NO_CONTENT)
    except Favorite.DoesNotExist:
        return Response({'error': 'Favorite not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f"Error in favorite_delete_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def merge_favorites_view(request):
    """
    Merge local favorites (product_ids, deal_ids) into the user's favorites.
    """
    try:
        product_ids = request.data.get('product_ids', [])
        deal_ids = request.data.get('deal_ids', [])
        user = request.user

        # Create favorites for each product/deal ID
        print('merging')
        
        for pid in product_ids:
            if pid and Product.objects.filter(id=pid).exists():
                Favorite.objects.get_or_create(user=user, product_id=pid)
        for did in deal_ids:
            if did and Deal.objects.filter(id=did).exists():
                Favorite.objects.get_or_create(user=user, deal_id=did)
        print('merging 2')
        
        # Delete user=null favorites for these IDs to avoid duplicates
        print(Favorite.objects.filter(user__isnull=True,product__id__in=product_ids))
        print(Favorite.objects.filter(user__isnull=True))
        print(Favorite.objects.filter(product__id__in=product_ids))
        Favorite.objects.filter(
            user__isnull=True, product__id__in=product_ids
        ).delete()
        Favorite.objects.filter(
            user__isnull=True, deal__id__in=deal_ids
        ).delete()
        print('merging complete')
        

        # Return updated favorites
        favorites = Favorite.objects.filter(user=user)
        serializer = FavoriteSerializer(favorites, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        print(f"Error in merge_favorites_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    finally:
        close_old_connections()
    
@api_view(['GET'])
def get_available_time_slots(request):
    try:
        branch_ids = request.query_params.get('branch_ids')  # Expect branch_ids as query param
        if not branch_ids:
            return Response({"error": "branch_ids parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.localtime(timezone.now())
        today = now.date()
        time_slots = []

        # Filter branches that are currently open
        branches = Branch.objects.filter(id__in=branch_ids.split(','))
        open_branches = [branch for branch in branches if branch.is_open()]

        if not open_branches:
            return Response({"error": "No branches are currently open"}, status=status.HTTP_400_BAD_REQUEST)

        # Find the branch that closes the latest
        latest_closing_branch = max(open_branches, key=lambda b: b.closing_time or timezone.make_aware(datetime.strptime("23:59", "%H:%M")).time())
        opening_time = latest_closing_branch.opening_time or timezone.make_aware(datetime.strptime("00:00", "%H:%M")).time()
        closing_time = latest_closing_branch.closing_time or timezone.make_aware(datetime.strptime("23:59", "%H:%M")).time()

        # Convert times to datetime
        start_dt = timezone.make_aware(datetime.combine(today, opening_time))
        
        # Check if closing time is before opening time (indicating next day)
        if closing_time <= opening_time:
            end_dt = timezone.make_aware(datetime.combine(today + timedelta(days=1), closing_time))
        else:
            end_dt = timezone.make_aware(datetime.combine(today, closing_time))

        # Adjust start time to now if it's later than opening time
        if now > start_dt:
            start_dt = now

        # Generate 30-minute intervals
        current_dt = start_dt
        while current_dt < end_dt:
            next_dt = current_dt + timedelta(minutes=30)
            if next_dt > now:  # Only include future slots
                time_slots.append({
                    "start": current_dt.strftime("%H:%M"),
                    "end": min(next_dt, end_dt).strftime("%H:%M"),
                    "value": current_dt.isoformat()  # For saving
                })
            current_dt = next_dt

        return Response({
            "branch_id": latest_closing_branch.id,
            "time_slots": time_slots
        }, status=status.HTTP_200_OK)
    except Exception as e:
        print(f"Error: {e}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def cart_create_view(request):
    try:
        auth_header = request.headers.get("Authorization")
        
        if not auth_header.startswith("Bearer "):
            return Response({"message": "Invalid token format"}, status=status.HTTP_401_UNAUTHORIZED)
        
        token = auth_header.split(" ")[1]  # Extract JWT
        user_id = decode_jwt(token)  # Decode JWT
        
        if not user_id:
            return Response({"message": "Invalid or expired token"}, status=status.HTTP_401_UNAUTHORIZED)
        
        request.user = User.objects.get(id=user_id)
    except Exception as e:
        print(f"Error in cart_create_view: {e}")
    
    cart = Cart.objects.create(user=request.user)

    return Response({"message": "Success", "cart": cart})


# Cart-related endpoints

# views.py
@api_view(['GET'])
def get_cart(request):
    """Retrieve the user's cart (or anonymous if not authenticated)."""
    cart_id = request.query_params.get('cart_id')
    auth_header = request.headers.get('Authorization', '')

    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        user_id = decode_jwt(token)

        if user_id:
            # Authenticated user
            carts = Cart.objects.filter(user_id=user_id).prefetch_related('cartitem_set', 'cartoffer_set__offer')
            
            if not cart_id:  # No cart_id provided: Delete existing cart and return "no cart"
                if carts.exists():
                    carts.delete()  # Delete all carts for this user (assumes one cart per user)
                return Response({'error': 'No cart found for user'}, status=status.HTTP_404_NOT_FOUND)
            
            # If cart_id is provided, fetch or merge
            if cart_id:
                try:
                    cart = Cart.objects.get(id=cart_id, user__isnull=True)  # Check if it's an anonymous cart
                    if carts.exists():
                        carts.delete()
                    cart.user_id = user_id  # Associate with user (merge)
                    cart.save()
                    
                    return Response(CartSerializer(cart).data)
                except Cart.DoesNotExist:
                    # If cart_id is invalid, check user's existing cart
                    if carts.exists():
                        try:
                            serializer = CartSerializer(carts.first())
                            return Response(serializer.data)
                        except Exception as e:
                            print(e)
                    return Response({'error': 'Cart not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                # Shouldn't reach here due to earlier no-cart_id check, but kept for clarity
                if carts.exists():
                    serializer = CartSerializer(carts.first())
                    return Response(serializer.data)
                return Response({'error': 'No cart found for user'}, status=status.HTTP_404_NOT_FOUND)
    
    else:
        # Unauthenticated: Fetch by cart_id
        if not cart_id:
            return Response({'error': 'Cart ID required for unauthenticated users'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            cart = Cart.objects.get(id=cart_id)  # Ensure it's anonymous
            serializer = CartSerializer(cart)
            return Response(serializer.data)
        except Cart.DoesNotExist:
            return Response({'error': 'Cart not found'}, status=status.HTTP_404_NOT_FOUND)
        finally:
         close_old_connections()
        
@api_view(['POST'])
def create_cart(request):
    """Create a new cart, optionally tied to an authenticated user."""
    auth_header = request.headers.get('Authorization', '')
    user_id = None
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        user_id = decode_jwt(token)
        if not user_id:
            return Response({'error': 'User not found'}, status=status.HTTP_401_UNAUTHORIZED)
    try:
        cart = Cart.objects.create(user_id=user_id)
        return Response(CartSerializer(cart).data, status=status.HTTP_201_CREATED)
    except Exception as e:
        print(f"Error in create_cart: {e}")


@api_view(['POST'])
def add_item_to_cart(request, cart_id):
    """
    Add an item (product or deal) to the cart, handling customizations and expandable choices.
    Optimized for performance with caching and indexing.
    """
    # Attempt to retrieve the cart by ID; return 404 if not found
    try:
        cart = Cart.objects.get(id=cart_id)
    except Cart.DoesNotExist:
        cart = Cart.objects.create()
        # return Response({'error': 'Cart not found'}, status=status.HTTP_404_NOT_FOUND)

    # Extract request data: product/deal ID, quantity, customizations, and expandable choices
    product_id = request.data.get('product_id')
    deal_id = request.data.get('deal_id')
    total_price = request.data.get('total_price')
    quantity = request.data.get('quantity', 1)
    customizations = request.data.get('customizations', [])  # List of {'customization_choice_id': int, 'price': float}
    expandable_choices = request.data.get('expandable_choices', [])  # List of {'expandable_choice_id': int, 'price': float}
    # Validate that either product_id or deal_id is provided
    if not (product_id or deal_id):
        return Response({'error': 'Product or Deal ID required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Determine if we're adding a product or deal and set filters accordingly
        if product_id:
            product = Product.objects.get(id=product_id)
            item_filter = {'product': product, 'deal': None}
            item_id = f"Product-{product_id}"
        elif deal_id:
            deal = Deal.objects.get(id=deal_id)
            item_filter = {'deal': deal, 'product': None}
            item_id = f"Deal-{deal_id}"

        # Generate a signature from the request data to identify this item uniquely
        # Sort IDs to ensure consistent signature regardless of input order
        # Generate signature (include deal product customizations for uniqueness)
        customization_ids = sorted([f"{c['deal_product_id'] or 'none'}:{c['customization_choice_id']}" for c in customizations])
        expandable_ids = sorted([f"{e['deal_product_id'] or 'none'}:{e['expandable_choice_id']}" for e in expandable_choices])
        # signature = "|".join([item_id, ":".join(customization_ids), ":".join(expandable_ids)])
        signature = "|".join([
            item_id,  # e.g., "Product-1"
            ":".join(map(str, customization_ids)),  # e.g., "1:2"
            ":".join(map(str, expandable_ids))  # e.g., "3"
        ])
        

        # Define a cache key specific to this cart's items
        cache_key = f"cart_{cart_id}_items_signatures"
        
        # Attempt to retrieve cached signatures for this cart
        cached_signatures = cache.get(cache_key)
        
        

        # If cache is empty, fetch items and populate the cache
        if cached_signatures is None:
            # Fetch all non-free items in the cart with related data in one query
            cart_items = CartItem.objects.filter(cart=cart, is_free=False).prefetch_related(
                'cartitemcustomization_set', 'cartitemexpandablechoice_set'
            )
            # Compute signatures for all items and store in cache
            cached_signatures = {item.id: item.get_signature() for item in cart_items}
            # Cache for 10 minutes (600 seconds) to balance freshness and performance
            cache.set(cache_key, cached_signatures, timeout=600)
        else:
            # If cache exists, fetch items without prefetching (we'll use cached signatures)
            cart_items = CartItem.objects.filter(cart=cart, is_free=False)
        
        # Look for an existing CartItem with a matching signature
        cart_item = None
        for item in cart_items:
            # Use cached signature if available, otherwise compute it
            item_signature = cached_signatures.get(item.id) or item.get_signature()
            if item_signature == signature:
                cart_item = item
                break
        
        

        # Perform database operations in a transaction for consistency
        with transaction.atomic():
            if cart_item:
                # If a matching item exists, increment its quantity
                cart_item.quantity += int(quantity)
                cart_item.save()
            else:
                # If no match, create a new CartItem
                cart_item = CartItem.objects.create(cart=cart, **item_filter, quantity=quantity, is_free=False)
                
                if deal_id:
                    deal_products = {dp.id: dp for dp in DealProduct.objects.filter(deal=deal)}
                    
                    for customization in customizations:
                        deal_product_id = customization.get('deal_product_id')
                        deal_product = deal_products.get(deal_product_id) if deal_product_id else None
                        CartItemCustomization.objects.create(
                            cart_item=cart_item,
                            customization_choice_id=customization['customization_choice_id'],
                            deal_product=deal_product,
                            price=Decimal(str(customization['price'])),
                            original_price=Decimal(str(customization['original_price']))
                        )
                    for expandable in expandable_choices:
                        deal_product_id = expandable.get('deal_product_id')
                        deal_product = deal_products.get(deal_product_id) if deal_product_id else None
                        CartItemExpandableChoice.objects.create(
                            cart_item=cart_item,
                            expandable_choice_id=expandable['expandable_choice_id'],
                            deal_product=deal_product,
                            price=Decimal(str(expandable['price']))
                        )
                else:
                # Add customizations with prices from request data (ensures price consistency at add-time)
                    for customization in customizations:
                        CartItemCustomization.objects.create(
                            cart_item=cart_item,
                            customization_choice_id=customization['customization_choice_id'],
                            price=Decimal(str(customization['price'])),
                            original_price=Decimal(str(customization['original_price']))
                        )
                    
                    # Add expandable choices with prices from request data
                    for expandable in expandable_choices:
                        CartItemExpandableChoice.objects.create(
                            cart_item=cart_item,
                            expandable_choice_id=expandable['expandable_choice_id'],
                            price=Decimal(str(expandable['price']))
                        )
                    
                cart_item.calculate_unit_prices(total_price)  # Set prices after customizations
                cart_item.save()
                # Update the cache with the new item's signature
                cached_signatures[cart_item.id] = cart_item.get_signature()
                cache.set(cache_key, cached_signatures, timeout=600)
                

            # Apply any automatic offers (assumed to handle free items separately)
            _apply_auto_offers(cart)
            

        # Serialize and return the updated cart
        serializer = CartSerializer(cart)
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    except (Product.DoesNotExist, Deal.DoesNotExist):
        # Handle case where product or deal doesn’t exist
        return Response({'error': 'Item not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        # Log and return any unexpected errors
        print(f"Error in add_item_to_cart: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    finally:
         close_old_connections()
    

@api_view(['PUT'])
def update_item_in_cart(request, cart_id, item_id):
    """
    Update an existing item in the cart, replacing its quantity, customizations, and expandable choices.
    If an identical item exists (same signature), merge by increasing the existing item's quantity.
    Optimized with caching and indexing, consistent with add_item_to_cart.
    """
    # Retrieve the cart by ID
    try:
        cart = Cart.objects.get(id=cart_id)
    except Cart.DoesNotExist:
        return Response({'error': 'Cart not found'}, status=status.HTTP_404_NOT_FOUND)

    # Retrieve the specific CartItem by ID
    try:
        cart_item = CartItem.objects.get(id=item_id, cart=cart)
    except CartItem.DoesNotExist:
        return Response({'error': 'Cart item not found'}, status=status.HTTP_404_NOT_FOUND)

    # Extract request data
    product_id = request.data.get('product_id')
    total_price = request.data.get('total_price')
    deal_id = request.data.get('deal_id')
    quantity = request.data.get('quantity', cart_item.quantity)  # Default to current if not provided
    customizations = request.data.get('customizations', [])  # List of {'customization_choice_id': int, 'price': float, 'original_price': float}
    expandable_choices = request.data.get('expandable_choices', [])  # List of {'expandable_choice_id': int, 'price': float}

    # Validate product or deal matches the existing item
    if product_id and cart_item.product and cart_item.product.id != int(product_id):
        return Response({'error': 'Product ID mismatch'}, status=status.HTTP_400_BAD_REQUEST)
    if deal_id and cart_item.deal and cart_item.deal.id != int(deal_id):
        return Response({'error': 'Deal ID mismatch'}, status=status.HTTP_400_BAD_REQUEST)
    if not (product_id or deal_id):
        return Response({'error': 'Product or Deal ID required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Determine item type and set filters
        if product_id:
            product = Product.objects.get(id=product_id)
            item_filter = {'product': product, 'deal': None}
            item_id_str = f"Product-{product_id}"
        elif deal_id:
            deal = Deal.objects.get(id=deal_id)
            item_filter = {'deal': deal, 'product': None}
            item_id_str = f"Deal-{deal_id}"

        # Generate signature for the updated item
        customization_ids = sorted([f"{c['deal_product_id'] or 'none'}:{c['customization_choice_id']}" for c in customizations])
        expandable_ids = sorted([f"{e['deal_product_id'] or 'none'}:{e['expandable_choice_id']}" for e in expandable_choices])
        signature = "|".join([
            item_id_str,  # e.g., "Product-1"
            ":".join(map(str, customization_ids)),  # e.g., "1:2"
            ":".join(map(str, expandable_ids))  # e.g., "3"
        ])

        # Cache key for cart items
        cache_key = f"cart_{cart_id}_items_signatures"
        cached_signatures = cache.get(cache_key)

        # If cache is empty, fetch and populate
        if cached_signatures is None:
            cart_items = CartItem.objects.filter(cart=cart, is_free=False).prefetch_related(
                'cartitemcustomization_set', 'cartitemexpandablechoice_set'
            )
            cached_signatures = {item.id: item.get_signature() for item in cart_items}
            cache.set(cache_key, cached_signatures, timeout=600)
        else:
            cart_items = CartItem.objects.filter(cart=cart, is_free=False)

        # Check for an existing item with the same signature (excluding this item)
        matching_item = None
        for item in cart_items:
            if item.id == cart_item.id:
                continue  # Skip the item being updated
            item_signature = cached_signatures.get(item.id) or item.get_signature()
            if item_signature == signature:
                matching_item = item
                break

        # Perform updates in a transaction
        with transaction.atomic():
            if matching_item:
                # Merge: Increase the existing item's quantity and delete the original item
                matching_item.quantity += int(quantity)
                matching_item.save()
                cart_item.delete()  # Delete the original item

                # Update cache: Remove the original item and keep the matching item's signature
                cached_signatures.pop(cart_item.id, None)
                cached_signatures[matching_item.id] = matching_item.get_signature()
                cache.set(cache_key, cached_signatures, timeout=600)
            else:
                # No match found, update the original item in place
                cart_item.quantity = int(quantity)

                # Clear existing customizations and expandable choices
                cart_item.cartitemcustomization_set.all().delete()
                cart_item.cartitemexpandablechoice_set.all().delete()

                # Add new customizations and expandable choices
                if deal_id:
                    deal_products = {dp.id: dp for dp in DealProduct.objects.filter(deal=deal)}
                    for customization in customizations:
                        deal_product_id = customization.get('deal_product_id')
                        deal_product = deal_products.get(deal_product_id) if deal_product_id else None
                        CartItemCustomization.objects.create(
                            cart_item=cart_item,
                            customization_choice_id=customization['customization_choice_id'],
                            deal_product=deal_product,
                            price=Decimal(str(customization['price'])),
                            original_price=Decimal(str(customization['original_price']))
                        )
                    for expandable in expandable_choices:
                        deal_product_id = expandable.get('deal_product_id')
                        deal_product = deal_products.get(deal_product_id) if deal_product_id else None
                        CartItemExpandableChoice.objects.create(
                            cart_item=cart_item,
                            expandable_choice_id=expandable['expandable_choice_id'],
                            deal_product=deal_product,
                            price=Decimal(str(expandable['price']))
                        )
                else:
                    for customization in customizations:
                        CartItemCustomization.objects.create(
                            cart_item=cart_item,
                            customization_choice_id=customization['customization_choice_id'],
                            price=Decimal(str(customization['price'])),
                            original_price=Decimal(str(customization['original_price']))
                        )
                    for expandable in expandable_choices:
                        CartItemExpandableChoice.objects.create(
                            cart_item=cart_item,
                            expandable_choice_id=expandable['expandable_choice_id'],
                            price=Decimal(str(expandable['price']))
                        )

                cart_item.calculate_unit_prices(total_price)  # Set prices after customizations
                cart_item.save()

                # Update cache
                cached_signatures[cart_item.id] = cart_item.get_signature()
                cache.set(cache_key, cached_signatures, timeout=600)

            # Reapply auto offers
            _apply_auto_offers(cart)

        # Serialize and return updated cart
        serializer = CartSerializer(cart)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except (Product.DoesNotExist, Deal.DoesNotExist):
        return Response({'error': 'Item not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f"Error in update_item_in_cart: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    
@api_view(['GET'])
def get_offer_by_code(request):
    code = request.query_params.get('code')
    try:
        offer = Offer.objects.get(code=code, is_active=True, valid_from__lte=timezone.now(), valid_until__gte=timezone.now())
        serializer = OfferSerializer(offer)
        return Response(serializer.data)
    except Offer.DoesNotExist:
        return Response({'error': 'Offer not found or expired'}, status=status.HTTP_404_NOT_FOUND)
    
def _apply_auto_offers(cart):
    current_subtotal = sum(item.subtotal or Decimal('0.00') for item in cart.cartitem_set.all()) or Decimal('0.00')
    current_delivery_fee = cart.branch.delivery_fee if cart.branch else Decimal('5.00')
    current_tax = current_subtotal * Decimal('0.10')
    base_total_value = current_subtotal + current_delivery_fee + current_tax
    try:
        # Clean up invalid offers
        for cart_offer in cart.cartoffer_set.filter(applied_by_user=False):
            if cart_offer.offer.min_spend and base_total_value < cart_offer.offer.min_spend:
                cart_offer.delete()

        # Fetch auto-applied offers
        offers = Offer.objects.filter(
            valid_from__lte=timezone.now(),
            valid_until__gte=timezone.now(),
            auto_apply=True
        )
        for offer in offers:
            # Handle FLASH_SALE with strict eligibility
            if offer.offer_type == 'FLASH_SALE':
                applies_to_cart = False
                for item in cart.cartitem_set.filter(is_free=False):
                    if (item.product and offer.applicable_products.exists() and item.product in offer.applicable_products.all()) or \
                    (item.deal and offer.applicable_deals.exists() and item.deal in offer.applicable_deals.all()):
                        applies_to_cart = True
                        break
                    elif not offer.applicable_products.exists() and not offer.applicable_deals.exists():
                        if (item.product and item.product.flash_sale_discount is not None) or \
                        (item.deal and item.deal.flash_sale_discount is not None):
                            applies_to_cart = True
                            break
                if applies_to_cart and (offer.min_spend is None or base_total_value >= offer.min_spend):
                    CartOffer.objects.get_or_create(
                        cart=cart,
                        offer=offer,
                        defaults={'applied_by_user': False}
                    )
            # Handle other auto-applied offers (e.g., PERCENTAGE, FLAT)
            elif (offer.min_spend is None or base_total_value >= offer.min_spend) and \
                (offer.usage_limit is None or offer.usage_count < offer.usage_limit):
                CartOffer.objects.get_or_create(
                    cart=cart,
                    offer=offer,
                    defaults={'applied_by_user': False}
                )
                
                if offer.offer_type in ['BOGO', 'FREE_ITEM']:
                    _apply_free_item_offer(cart, offer)
    except Exception as e:
        print(e)
                
@api_view(['POST'])
def merge_cart(request):
    """Merge an anonymous cart into the authenticated user's cart, or return the existing cart if cart_id matches."""
    
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

    token = auth_header.split(' ')[1]
    user_id = decode_jwt(token)
    if not user_id:
        return Response({'error': 'Invalid or expired token'}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        user = User.objects.get(id=user_id)
    except Exception as e:
        print(f'error at user: {e}')
        return Response({'error': 'User not found'}, status=status.HTTP_401_UNAUTHORIZED)
    
    anonymous_cart_id = request.data.get('cart_id')
    if not anonymous_cart_id:
        return Response({'error': 'Cart ID is required'}, status=status.HTTP_400_BAD_REQUEST)

    
    try:
        # Check if the provided cart_id already belongs to the user
        user_carts = Cart.objects.filter(user_id=user_id)
        
        if user_carts.filter(id=anonymous_cart_id).exists():
            
            # The cart_id is already the user's cart, no merge needed
            user_cart = user_carts.get(id=anonymous_cart_id)
            
            return Response(CartSerializer(user_cart).data)

        # Fetch the anonymous cart (must be user__isnull=True)
        try:
            anonymous_cart = Cart.objects.get(id=anonymous_cart_id, user__isnull=True)
            
        except Cart.DoesNotExist:
            return Response({'error': 'Anonymous cart not found'}, status=status.HTTP_404_NOT_FOUND)

        if user_carts.exists():
            # User has an existing cart: Merge anonymous cart into it
            user_cart = user_carts.delete()
            
            # # Merge items
            # for anon_item in anonymous_cart.cartitem_set.all():
            #     user_item, created = CartItem.objects.get_or_create(
            #         cart=user_cart,
            #         product=anon_item.product,
            #         deal=anon_item.deal,
            #         defaults={'quantity': anon_item.quantity}
            #     )
            #     if not created:
            #         user_item.quantity += anon_item.quantity
            #         user_item.save()
                
            #     for anon_customization in anon_item.cartitemcustomization_set.all():
            #         CartItemCustomization.objects.get_or_create(
            #             cart_item=user_item,
            #             customization_choice=anon_customization.customization_choice,
            #             defaults={'price': anon_customization.price, 'originalPrice': anon_customization.originalPrice}
            #         )

            #     for anon_expandable in anon_item.cartitemexpandablechoice_set.all():
            #         CartItemExpandableChoice.objects.get_or_create(
            #             cart_item=user_item,
            #             expandable_choice=anon_expandable.expandable_choice,
            #             defaults={'price': anon_expandable.price}
            #         )
            
            # # Merge offers
            # for anon_offer in anonymous_cart.cartoffer_set.all():
            #     CartOffer.objects.get_or_create(
            #         cart=user_cart,
            #         offer=anon_offer.offer,
            #         defaults={'applied_by_user': anon_offer.applied_by_user}
            #     )
            
            # Delete the anonymous cart after merging
            anonymous_cart.delete()
        else:
            # No existing user cart: Assign the anonymous cart to the user
            anonymous_cart.user_id = user.id
            anonymous_cart.save()
            user_cart = anonymous_cart
        
        return Response(CartSerializer(user_cart).data)
    
    except Exception as e:
        print(f"Error during merge: {e}")
        return Response({'error': 'An error occurred during merge'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
# Order-related endpoints

@api_view(['GET'])
def get_orders(request):
    """Retrieve all orders for the authenticated user."""
    try:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            user_id = decode_jwt(token)
            if user_id == None:
                return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        orders = Order.objects.filter(user=request.user).prefetch_related('orderitem_set')
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)
    except Exception as e:
        print(e)


@api_view(['POST'])
def create_order(request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

    token = auth_header.split(' ')[1]
    user_id = decode_jwt(token)
    if not user_id:
        return Response({'error': 'Invalid token'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        serializer = OrderCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            order = serializer.save()
            Invoice.objects.create(order=order, total_amount=order.total_amount)
            return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)
    except Exception as e:
        print(f'error in create_order: {e}')
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

# views.py
@api_view(['GET'])
def get_available_offers(request, cart_id):
    try:
        cart = Cart.objects.get(id=cart_id)
    except Cart.DoesNotExist:
        return Response({'error': 'Cart not found'}, status=status.HTTP_404_NOT_FOUND)
    try:
        cart_total = cart.base_total
        offers = Offer.objects.filter(
            valid_from__lte=timezone.now(),
            valid_until__gte=timezone.now()
        ).exclude(cartoffer__cart=cart)  # Exclude already applied offers
        available = []
        near_unlock = []

        for offer in offers:
            # Check general usage limit
            if offer.usage_limit is not None and offer.usage_count >= offer.usage_limit:
                continue

            # Check user-specific usage limit
            if cart.user and UserOfferUsage.objects.filter(user=cart.user, offer=offer).exists():
                
                
                user_usage = UserOfferUsage.objects.get(user=cart.user, offer=offer)
                if offer.per_user_limit and user_usage.usage_count >= offer.per_user_limit:
                    continue
            # Special handling for FLASH_SALE
            if offer.offer_type == 'FLASH_SALE':
                
                applies_to_cart = False
                for item in cart.cartitem_set.filter(is_free=False):
                    if (item.product and offer.applicable_products.exists() and item.product in offer.applicable_products.all()) or \
                       (item.deal and offer.applicable_deals.exists() and item.deal in offer.applicable_deals.all()):
                        applies_to_cart = True
                        break
                    # elif not offer.applicable_products.exists() and not offer.applicable_deals.exists():
                    #     if (item.product and item.product.flash_sale_discount is not None) or \
                    #        (item.deal and item.deal.flash_sale_discount is not None):
                    #         applies_to_cart = True
                    #         break
                # Only add to available if the cart has eligible items
                if applies_to_cart:
                    if offer.min_spend:
                        if cart_total >= offer.min_spend:
                            available.append(offer)
                        elif offer.near_unlock_threshold and (offer.min_spend - cart_total) <= offer.near_unlock_threshold:
                            near_unlock.append(offer)
                    else:
                        available.append(offer)
            # Standard logic for other offer types
            
            else:
                
                if offer.min_spend:
                    if cart_total >= offer.min_spend:
                        available.append(offer)
                    elif offer.near_unlock_threshold and (offer.min_spend - cart_total) <= offer.near_unlock_threshold:
                        near_unlock.append(offer)
                else:
                    available.append(offer)

        return Response({
            'available': OfferSerializer(available, many=True).data,
            'near_unlock': OfferSerializer(near_unlock, many=True).data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        print(f"Error in get_available_offers: {e}")
        return Response({'error': f'An error occurred: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def apply_offer(request, cart_id):
    try:
        cart = Cart.objects.get(id=cart_id)
        offer_id = request.data.get('offer_id')
        offer = Offer.objects.get(id=offer_id)
        
        # Check basic offer validity
        if not (offer.valid_from <= timezone.now() <= offer.valid_until and offer.is_active):
            return Response({'error': 'Offer expired or inactive'}, status=status.HTTP_400_BAD_REQUEST)
        if offer.min_spend and cart.base_total < offer.min_spend:
            return Response({'error': 'Cart total too low'}, status=status.HTTP_400_BAD_REQUEST)
        if offer.usage_limit and offer.usage_count >= offer.usage_limit:
            return Response({'error': 'Offer usage limit reached'}, status=status.HTTP_400_BAD_REQUEST)

        # User-specific validation
        user = cart.user
        if user:
            user_usage, _ = UserOfferUsage.objects.get_or_create(user=user, offer=offer)
            if offer.usage_scope == 'SINGLE_USER' and user_usage.usage_count >= offer.per_user_limit:
                return Response({'error': 'Offer already used by this user'}, status=status.HTTP_400_BAD_REQUEST)
            if offer.per_user_limit and user_usage.usage_count >= offer.per_user_limit:
                return Response({'error': 'User redemption limit reached'}, status=status.HTTP_400_BAD_REQUEST)

        
        # Remove existing manual offer and its free items
        existing_manual = cart.cartoffer_set.filter(applied_by_user=True)
        if existing_manual.exists():
            for manual_offer in existing_manual:
               cart.cartitem_set.filter(
            models.Q(product__in=manual_offer.offer.free_products.all()) | 
            models.Q(deal__in=manual_offer.offer.free_deals.all()),
            is_free=True
        ).delete()
            existing_manual.delete()
        # Handle BOGO and FREE_ITEM offers
        if offer.offer_type in ['BOGO', 'FREE_ITEM']:
            _apply_free_item_offer(cart, offer)

        # Apply the new manual offer
        CartOffer.objects.get_or_create(cart=cart, offer=offer, defaults={'applied_by_user': True})
        return Response(CartSerializer(cart).data)
    except Exception as e:
        print(e)
        return Response({'error': 'Cart or offer not found'}, status=status.HTTP_404_NOT_FOUND)

def _apply_free_item_offer(cart, offer):
    """Apply BOGO or FREE_ITEM offers with multiple free products/deals."""
    if offer.offer_type == 'BOGO':
        for product in offer.free_products.all():
            paid_items = cart.cartitem_set.filter(product=product, is_free=False)
            if paid_items.exists():
                paid_item = paid_items.first()
                free_quantity = paid_item.quantity
                free_item = cart.cartitem_set.filter(product=product, is_free=True).first()
                if free_item:
                    free_item.quantity = free_quantity
                    free_item.save()
                else:
                    CartItem.objects.create(
                        cart=cart,
                        product=product,
                        quantity=free_quantity,
                        is_free=True
                    )
        for deal in offer.free_deals.all():
            paid_items = cart.cartitem_set.filter(deal=deal, is_free=False)
            if paid_items.exists():
                paid_item = paid_items.first()
                free_quantity = paid_item.quantity
                free_item = cart.cartitem_set.filter(deal=deal, is_free=True).first()
                if free_item:
                    free_item.quantity = free_quantity
                    free_item.save()
                else:
                    CartItem.objects.create(
                        cart=cart,
                        deal=deal,
                        quantity=free_quantity,
                        is_free=True
                    )

    elif offer.offer_type == 'FREE_ITEM' and cart.base_total >= offer.min_spend:
        desired_quantity = offer.free_item_quantity  # Number of each free item

        # Add all free products
        for product in offer.free_products.all():
            existing_free = cart.cartitem_set.filter(product=product, is_free=True).first()
            if existing_free:
                # Update quantity if it exists and differs
                if existing_free.quantity != desired_quantity:
                    existing_free.quantity = desired_quantity
                    existing_free.save()
            else:
                # Add new free item
                CartItem.objects.create(
                    cart=cart,
                    product=product,
                    quantity=desired_quantity,
                    is_free=True
                )

        # Add all free deals
        for deal in offer.free_deals.all():
            existing_free = cart.cartitem_set.filter(deal=deal, is_free=True).first()
            if existing_free:
                # Update quantity if it exists and differs
                if existing_free.quantity != desired_quantity:
                    existing_free.quantity = desired_quantity
                    existing_free.save()
            else:
                # Add new free item
                CartItem.objects.create(
                    cart=cart,
                    deal=deal,
                    quantity=desired_quantity,
                    is_free=True
                )


@api_view(['DELETE'])
def remove_item_from_cart(request, cart_id, item_id):
    """
    Remove a specific item from the cart.
    Requires authentication via Bearer token (optional for anonymous carts).
    Updates cache and returns the updated cart.
    """
    # Authentication handling
    auth_header = request.headers.get('Authorization', '')
    user_id = None
    
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        try:
            user_id = decode_jwt(token)
            if not user_id:
                return Response(
                    {'error': 'Invalid or expired token'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
        except Exception as e:
            print(f"Error decoding token: {e}")
            return Response(
                {'error': 'Authentication error'},
                status=status.HTTP_401_UNAUTHORIZED
            )

    # Fetch and validate cart
    try:
        cart = Cart.objects.get(id=cart_id)
        # If cart is associated with a user, ensure token matches
        if cart.user_id and cart.user_id != user_id:
            return Response(
                {'error': 'Unauthorized access to cart'},
                status=status.HTTP_403_FORBIDDEN
            )
    except Cart.DoesNotExist:
        return Response(
            {'error': 'Cart not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Fetch and remove the cart item
    try:
        cart_item = CartItem.objects.get(id=item_id, cart=cart)
    except CartItem.DoesNotExist:
        return Response(
            {'error': 'Cart item not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    try:
        with transaction.atomic():
            # Delete the item and its related customizations/expandable choices
            cart_item.cartitemcustomization_set.all().delete()
            cart_item.cartitemexpandablechoice_set.all().delete()
            cart_item.delete()

            # Update cache
            cache_key = f"cart_{cart_id}_items_signatures"
            cached_signatures = cache.get(cache_key)
            if cached_signatures and cart_item.id in cached_signatures:
                del cached_signatures[cart_item.id]
                cache.set(cache_key, cached_signatures, timeout=600)

            # Reapply auto offers since subtotal might have changed
            _apply_auto_offers(cart)

        # Serialize and return updated cart
        serializer = CartSerializer(cart)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except Exception as e:
        print(f"Error in remove_item_from_cart: {e}")
        return Response(
            {'error': f'Failed to remove item: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        
@api_view(['GET'])
def get_flash_sale_status(request):
    """Return the current flash sale status and details."""
    active_flash_sale = Offer.get_active_flash_sale()
    if active_flash_sale:
        serializer = OfferSerializer(active_flash_sale)
        return Response({
            'is_flash_sale_active': True,
            'flash_sale': serializer.data
        })
    return Response({'is_flash_sale_active': False, 'flash_sale': None})   
    
@api_view(['POST'])
def remove_offer(request, cart_id):
    try:
        cart = Cart.objects.get(id=cart_id)
        offer_id = request.data.get('offer_id')
        
        cart_offer = CartOffer.objects.get(cart=cart, offer_id=offer_id, applied_by_user=True)  # Only manual offers can be removed

        offer = Offer.objects.get(id=offer_id)

        _remove_free_items(cart, offer)
        cart_offer.delete()
        
        
        return Response(CartSerializer(cart).data)
    except (Cart.DoesNotExist, CartOffer.DoesNotExist):
        return Response({'error': 'Offer not applied or not removable'}, status=status.HTTP_400_BAD_REQUEST)
    
    
def _remove_free_items(cart, offer=None):
    if offer is None:
        return
    cart.cartitem_set.filter(
        models.Q(product__in=offer.free_products.all(), is_free=True) | 
        models.Q(deal__in=offer.free_deals.all(), is_free=True)
    ).delete()
    
    
@api_view(['PUT'])
def update_cart_item_quantity(request, cart_id, item_id):
    """
    Update the quantity of a CartItem. If quantity is 0, delete the item.
    If no paid items remain, delete the cart entirely.
    """
    try:
        # Fetch the cart and the specific cart item
        cart = Cart.objects.get(id=cart_id)
        cart_item = CartItem.objects.get(id=item_id, cart=cart)

        # Get the new quantity from the request
        new_quantity = request.data.get('quantity')
        if not isinstance(new_quantity, int) or new_quantity < 0:
            return Response({'error': 'Invalid quantity'}, status=status.HTTP_400_BAD_REQUEST)

        # Use a transaction to ensure atomicity
        with transaction.atomic():
            if new_quantity == 0:
                # Delete the specific cart item if quantity is 0
                cart_item.delete()

                # Check if any paid (non-free) items remain in the cart
                paid_items_exist = cart.cartitem_set.filter(is_free=False).exists()

                if not paid_items_exist:
                    # If no paid items remain, delete all free items and the cart itself
                    cart.cartitem_set.filter(is_free=True).delete()
                    cart.delete()
                    return Response(
                        {'message': 'cart_deleted'},  # Consistent message for full cart deletion
                        status=status.HTTP_200_OK   # Use 200 for simplicity; frontend expects this
                    )
                
                # If paid items still exist, just return the updated cart
                _apply_auto_offers(cart)
                serializer = CartSerializer(cart)
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                # Update the quantity if not 0
                cart_item.quantity = new_quantity
                cart_item.save()

            # Recalculate totals after quantity update
            current_subtotal = sum(item.subtotal or Decimal('0.00') for item in cart.cartitem_set.all()) or Decimal('0.00')
            current_delivery_fee = cart.branch.delivery_fee if cart.branch else Decimal('5.00')
            current_tax = current_subtotal * Decimal('0.10')
            base_total_value = current_subtotal + current_delivery_fee + current_tax

            # Remove offers if the total falls below min_spend
            for cart_offer in cart.cartoffer_set.all():
                offer = cart_offer.offer
                if offer.min_spend and base_total_value < offer.min_spend:
                    _remove_free_items(cart, offer)
                    cart_offer.delete()

            # Re-apply auto offers after updates
            _apply_auto_offers(cart)

            # Serialize and return the updated cart
            serializer = CartSerializer(cart)
            return Response(serializer.data, status=status.HTTP_200_OK)

    except Cart.DoesNotExist:
        return Response({'error': 'Cart not found'}, status=status.HTTP_404_NOT_FOUND)
    except CartItem.DoesNotExist:
        return Response({'error': 'Cart item not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f"Error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
@api_view(['POST'])
def create_booking(request):
    """Create a new booking."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

    token = auth_header.split(' ')[1]
    user_id = decode_jwt(token)
    if not user_id:
        return Response({'error': 'Invalid token'}, status=status.HTTP_401_UNAUTHORIZED)

    serializer = BookingSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(user_id=user_id)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
def get_bookings(request):
    """Retrieve user's bookings."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

    token = auth_header.split(' ')[1]
    user_id = decode_jwt(token)
    if not user_id:
        return Response({'error': 'Invalid token'}, status=status.HTTP_401_UNAUTHORIZED)

    bookings = Booking.objects.filter(user_id=user_id)
    serializer = BookingSerializer(bookings, many=True)
    return Response(serializer.data)


@api_view(['POST'])
def add_payment_method(request):
    """Add a payment method for the user."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

    token = auth_header.split(' ')[1]
    user_id = decode_jwt(token)
    if not user_id:
        return Response({'error': 'Invalid token'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        serializer = PaymentMethodSerializer(data=request.data)
        if serializer.is_valid():
            # Check if the payment method already exists
            existing_payment = PaymentMethod.objects.filter(
                user_id=user_id,
                payment_type=serializer.validated_data['payment_type'],
                last_four=serializer.validated_data['last_four'],
                expiry_month=serializer.validated_data['expiry_month'],
                expiry_year=serializer.validated_data['expiry_year']
            ).first()
            
            if existing_payment:
                
                # If the payment method exists, return it without saving a new one
                return Response(PaymentMethodSerializer(existing_payment).data, status=status.HTTP_200_OK)

            # Save new payment method
            new_payment = serializer.save(user_id=user_id)
            
            return Response(PaymentMethodSerializer(new_payment).data, status=status.HTTP_201_CREATED)

    except Exception as e:
        print(e)
        return Response({'error': 'Something went wrong'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def process_payment(request):
    """Process payment for an order or booking."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

    token = auth_header.split(' ')[1]
    user_id = decode_jwt(token)
    if not user_id:
        return Response({'error': 'Invalid token'}, status=status.HTTP_401_UNAUTHORIZED)

    order_id = request.data.get('order_id')
    booking_id = request.data.get('booking_id')
    payment_method_id = request.data.get('payment_method_id')
    amount = request.data.get('amount')

    try:
        payment_method = PaymentMethod.objects.get(id=payment_method_id, user_id=user_id)
        if order_id:
            order = Order.objects.get(id=order_id, user_id=user_id)
            transaction, created = Transaction.objects.get_or_create(
                order=order,
                defaults = {
                    "payment_method":payment_method,
                    "amount":amount,
                    "transaction_id":f"TXN-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                }
            )
            if created:
                invoice =  Invoice.objects.get(order=order)
                invoice.status = 'PAID'
                invoice.paid_at = timezone.now()
                transaction.invoice = invoice
                invoice.save()
                # Simulate payment success for non-COD
                if payment_method.payment_type != 'COD':
                    transaction.status = 'SUCCESS'
                    transaction.completed_at = timezone.now()
                    order.payment_status = 'PAID'
                    order.save()
                transaction.save()
        elif booking_id:
            booking = Booking.objects.get(id=booking_id, user_id=user_id)
            transaction, created = Transaction.objects.get_or_create(
                booking=booking,
                defaults={'payment_method':payment_method,
                'amount':amount,
                'transaction_id':f"TXN-{timezone.now().strftime('%Y%m%d%H%M%S')}",}
            )
            if not created:
                transaction.status = 'SUCCESS'
                transaction.completed_at = timezone.now()
                booking.status = 'CONFIRMED'
                booking.save()
                transaction.save()
        else:
            return Response({'error': 'Order or booking ID required'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(TransactionSerializer(transaction).data, status=status.HTTP_201_CREATED)
    except Exception as e:
        print(e)
        return Response({'error': 'Invalid order, booking, or payment method'}, status=status.HTTP_404_NOT_FOUND)
    
# @api_view(['POST'])
# def cancel_order_or_booking(request):
#     auth_header = request.headers.get('Authorization', '')
#     if not auth_header.startswith('Bearer '):
#         return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

#     token = auth_header.split(' ')[1]
#     user_id = decode_jwt(token)
#     if not user_id:
#         return Response({'error': 'Invalid token'}, status=status.HTTP_401_UNAUTHORIZED)

#     order_id = request.data.get('order_id')
#     booking_id = request.data.get('booking_id')
#     reason = request.data.get('reason')

#     try:
#         if order_id:
#             order = Order.objects.get(id=order_id, user_id=user_id)
#             if order.status in ['DELIVERED', 'CANCELLED']:
#                 print('sada')
                
#                 return Response({'error': 'Cannot cancel delivered or already cancelled order'}, status=status.HTTP_400_BAD_REQUEST)
#             transaction = Transaction.objects.filter(order=order, status='SUCCESS').first()
#             refund_amount = transaction.amount if transaction and (timezone.now() - order.created_at).total_seconds() < 3600 else Decimal('0.00')
#             cancellation = Cancellation.objects.create(order=order, reason=reason, refund_amount=refund_amount)
#             order.status = 'CANCELLED'
#             order.save()
#         elif booking_id:
#             booking = Booking.objects.get(id=booking_id, user_id=user_id)
#             if booking.status in ['COMPLETED', 'CANCELLED']:
#                 return Response({'error': 'Cannot cancel completed or already cancelled booking'}, status=status.HTTP_400_BAD_REQUEST)
#             transaction = Transaction.objects.filter(booking=booking, status='SUCCESS').first()
#             refund_amount = transaction.amount if transaction and (timezone.now() - booking.created_at).total_seconds() < 3600 else Decimal('0.00')
#             cancellation = Cancellation.objects.create(booking=booking, reason=reason, refund_amount=refund_amount)
#             booking.status = 'CANCELLED'
#             booking.save()
#         else:
#             return Response({'error': 'Order or booking ID required'}, status=status.HTTP_400_BAD_REQUEST)
#         print('gitit')
#         return Response(CancellationSerializer(cancellation).data, status=status.HTTP_201_CREATED)
#     except (Order.DoesNotExist, Booking.DoesNotExist):
#         print('gitiwwt')
        
#         return Response({'error': 'Invalid order or booking'}, status=status.HTTP_404_NOT_FOUND)
    
@api_view(['POST'])
def check_refund_amount(request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

    token = auth_header.split(' ')[1]
    user_id = decode_jwt(token)
    if not user_id:
        return Response({'error': 'Invalid token'}, status=status.HTTP_401_UNAUTHORIZED)

    order_id = request.data.get('order_id')
    booking_id = request.data.get('booking_id')

    try:
        if order_id:
            order = Order.objects.get(id=order_id, user_id=user_id)
            if order.status in ['DELIVERED', 'CANCELLED']:
                return Response(
                    {'error': 'Cannot check refund for delivered or cancelled order'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            transaction = Transaction.objects.filter(order=order, status='SUCCESS').first()
            if not transaction:
                return Response(
                    {'refund_amount': '0.00', 'original_amount': '0.00'},
                    status=status.HTTP_200_OK
                )
            time_elapsed = (timezone.now() - order.created_at).total_seconds() / 3600  # Hours
            original_amount = transaction.amount
            refund_amount = calculate_refund_amount(time_elapsed, original_amount)
            return Response(
                {
                    'refund_amount': str(refund_amount),
                    'original_amount': str(original_amount)
                },
                status=status.HTTP_200_OK
            )
        elif booking_id:
            booking = Booking.objects.get(id=booking_id, user_id=user_id)
            if booking.status in ['COMPLETED', 'CANCELLED']:
                return Response(
                    {'error': 'Cannot check refund for completed or cancelled booking'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            transaction = Transaction.objects.filter(booking=booking, status='SUCCESS').first()
            if not transaction:
                return Response(
                    {'refund_amount': '0.00', 'original_amount': '0.00'},
                    status=status.HTTP_200_OK
                )
            time_elapsed = (timezone.now() - booking.created_at).total_seconds() / 3600  # Hours
            original_amount = transaction.amount
            refund_amount = calculate_refund_amount(time_elapsed, original_amount)
            return Response(
                {
                    'refund_amount': str(refund_amount),
                    'original_amount': str(original_amount)
                },
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                {'error': 'Order or booking ID required'},
                status=status.HTTP_400_BAD_REQUEST
            )
    except (Order.DoesNotExist, Booking.DoesNotExist):
        return Response(
            {'error': 'Invalid order or booking'},
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['POST'])
def cancel_order_or_booking(request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

    token = auth_header.split(' ')[1]
    user_id = decode_jwt(token)
    if not user_id:
        return Response({'error': 'Invalid token'}, status=status.HTTP_401_UNAUTHORIZED)

    order_id = request.data.get('order_id')
    booking_id = request.data.get('booking_id')
    reason = request.data.get('reason')

    if not reason:
        return Response(
            {'error': 'Cancellation reason required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        if order_id:
            order = Order.objects.get(id=order_id, user_id=user_id)
            if order.status in ['DELIVERED', 'CANCELLED']:
                return Response(
                    {'error': 'Cannot cancel delivered or already cancelled order'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            transaction = Transaction.objects.filter(order=order, status='SUCCESS').first()
            refund_amount = Decimal('0.00')
            if transaction:
                time_elapsed = (timezone.now() - order.created_at).total_seconds() / 3600  # Hours
                refund_amount = calculate_refund_amount(time_elapsed, transaction.amount)
            cancellation = Cancellation.objects.create(
                order=order,
                reason=reason,
                refund_amount=refund_amount
            )
            order.status = 'CANCELLED'
            order.save()
        elif booking_id:
            booking = Booking.objects.get(id=booking_id, user_id=user_id)
            if booking.status in ['COMPLETED', 'CANCELLED']:
                return Response(
                    {'error': 'Cannot cancel completed or already cancelled booking'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            transaction = Transaction.objects.filter(booking=booking, status='SUCCESS').first()
            refund_amount = Decimal('0.00')
            if transaction:
                time_elapsed = (timezone.now() - booking.created_at).total_seconds() / 3600  # Hours
                refund_amount = calculate_refund_amount(time_elapsed, transaction.amount)
            cancellation = Cancellation.objects.create(
                booking=booking,
                reason=reason,
                refund_amount=refund_amount
            )
            booking.status = 'CANCELLED'
            booking.save()
        else:
            return Response(
                {'error': 'Order or booking ID required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return Response(
            CancellationSerializer(cancellation).data,
            status=status.HTTP_201_CREATED
        )
    except (Order.DoesNotExist, Booking.DoesNotExist):
        return Response(
            {'error': 'Invalid order or booking'},
            status=status.HTTP_404_NOT_FOUND
        )

def calculate_refund_amount(time_elapsed_hours, original_amount):
    """
    Refund policy inspired by food delivery apps like Uber Eats, DoorDash, Swiggy:
    - Within 1 hour: 100% refund
    - 1-3 hours: 50% refund
    - 3-6 hours: 25% refund
    - After 6 hours: No refund
    """
    if time_elapsed_hours <= 1:
        return original_amount * Decimal('0.50')
    elif time_elapsed_hours <= 3:
        return original_amount * Decimal('0.50')
    elif time_elapsed_hours <= 6:
        return original_amount * Decimal('0.25')
    else:
        return Decimal('0.00')
    
@api_view(['GET'])
def get_invoices(request):
    """Retrieve user's invoices."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

    token = auth_header.split(' ')[1]
    user_id = decode_jwt(token)
    if not user_id:
        return Response({'error': 'Invalid token'}, status=status.HTTP_401_UNAUTHORIZED)

    invoices = Invoice.objects.filter(models.Q(order__user_id=user_id) | models.Q(booking__user_id=user_id))
    serializer = InvoiceSerializer(invoices, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def get_payment_methods(request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

    token = auth_header.split(' ')[1]
    user_id = decode_jwt(token)
    if not user_id:
        return Response({'error': 'Invalid token'}, status=status.HTTP_401_UNAUTHORIZED)

    payment_methods = PaymentMethod.objects.filter(user_id=user_id)
    serializer = PaymentMethodSerializer(payment_methods, many=True)
    return Response(serializer.data)



@api_view(['POST'])
def create_payment_intent(request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

    token = auth_header.split(' ')[1]
    user_id = decode_jwt(token)
    if not user_id:
        return Response({'error': 'Invalid token'}, status=status.HTTP_401_UNAUTHORIZED)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            amount = data.get('amount', 1000)  # Amount in cents (e.g., $10.00)
            currency = data.get('currency', 'usd')

            # Create a Payment Intent
            intent = stripe.PaymentIntent.create(
                amount=amount,
                currency=currency,
                payment_method_types=['card'],
            )
            
            return JsonResponse({
                'payment_intent_id': intent['id'],
                'client_secret': intent['client_secret'],
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Invalid request'}, status=400)

# New endpoint to retrieve Payment Intent details
@api_view(['POST'])
def get_payment_intent(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            payment_intent_id = data.get('payment_intent_id')
            if not payment_intent_id:
                return JsonResponse({'error': 'Payment Intent ID is required'}, status=400)

            # Retrieve Payment Intent from Stripe
            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            # Return relevant details
            return JsonResponse({
                'id': payment_intent['id'],
                'amount': payment_intent['amount'],
                'currency': payment_intent['currency'],
                'status': payment_intent['status'],
                'payment_method_types': payment_intent['payment_method_types'],
                'created': payment_intent['created'],
                'charge_id': payment_intent['latest_charge'],
                'last_payment_error': payment_intent.get('last_payment_error', None),
            })
        except stripe.error.StripeError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': 'An unexpected error occurred'}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)

# brainy-pros-clear-awards
@api_view(['POST'])
def get_charge_details(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            charge_id = data.get('charge_id')

            if not charge_id:
                return JsonResponse({'error': 'Charge ID is required'}, status=400)

            # Retrieve Payment Intent from Stripe
            charge = stripe.Charge.retrieve(charge_id)
            
            # Return relevant details
            return JsonResponse({
                'message': charge['outcome']['seller_message'],
                'customer_country_code': charge['billing_details']['address']['country'],
                'is_paid':charge['paid'],
                'card_brand':charge['payment_method_details']['card']['brand'],
                'card_country':charge['payment_method_details']['card']['country'],
                'card_exp_month':charge['payment_method_details']['card']['exp_month'],
                'card_exp_year':charge['payment_method_details']['card']['exp_year'],
                'card_last4':charge['payment_method_details']['card']['last4'],
                'status':charge['status'],
                'currency':charge['currency'],
                'card_type':charge['payment_method_details']['card']['funding'],
            })
        except stripe.error.StripeError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': 'An unexpected error occurred'}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)


@api_view(["POST"])
def stripe_webhook(request):
    payload = request.body
    # Parse the event (no signature verification for now, just testing)
    event = json.loads(payload)
    event_type = event['type']
    if event_type == 'charge.succeeded' or event_type == 'charge.updated':
        print('yessss')
    if event_type == 'payment_intent.succeeded':
        print("Payment succeeded!")
    elif event_type == 'payment_intent.payment_failed':
        print("Payment failed!")

    return HttpResponse(status=200)


@api_view(['GET'])
def branch_list_view(request):
    try:
        branches = Branch.objects.filter(is_active=True)
        serializer = BranchSerializer(branches, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        print(f"Error in branch_list_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def branch_detail_view(request, branch_id):
    try:
        branch = Branch.objects.get(id=branch_id, is_active=True)
        serializer = BranchSerializer(branch)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Branch.DoesNotExist:
        return Response({'error': 'Branch not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f"Error in branch_detail_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
def branch_status_bulk_view(request):
    try:
        branch_ids = request.query_params.get('branch_ids', None)
        if not branch_ids:
            return Response({'message': 'No branch available nearby'}, status=status.HTTP_200_OK)
        
        branch_ids = [int(id) for id in branch_ids.split(',')]
        branches = Branch.objects.filter(id__in=branch_ids, is_active=True)
        
        if not branches.exists():
            return Response({'message': 'No branch available nearby'}, status=status.HTTP_200_OK)
        
        # Check if any branch is open
        any_open = any(branch.is_open() for branch in branches)
        return Response({'message': '' if any_open else 'Closed'}, status=status.HTTP_200_OK)
    except Exception as e:
        print(f"Error in branch_status_bulk_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
def branch_deals_view(request, branch_id):
    try:
        branch = Branch.objects.get(id=branch_id, is_active=True)
        unavailable_deals = DealBranchStock.objects.filter(branch=branch, is_available=False).values_list('deal_id', flat=True)
        deals = Deal.objects.exclude(id__in=unavailable_deals)
        serializer = DealSerializer(deals, many=True, context={'branch_id': branch_id})
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Branch.DoesNotExist:
        return Response({'error': 'Branch not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f"Error in branch_deals_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def branch_stock_status_view(request, branch_id):
    try:
        branch = Branch.objects.get(id=branch_id, is_active=True)
        product_stock = ProductBranchStock.objects.filter(branch=branch)
        deal_stock = DealBranchStock.objects.filter(branch=branch)
        product_serializer = ProductBranchStockSerializer(product_stock, many=True)
        deal_serializer = DealBranchStockSerializer(deal_stock, many=True)
        return Response({
            'products': product_serializer.data,
            'deals': deal_serializer.data
        }, status=status.HTTP_200_OK)
    except Branch.DoesNotExist:
        return Response({'error': 'Branch not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f"Error in branch_stock_status_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    
@api_view(['GET'])
def branch_products_view(request, branch_id):
    try:
        branch = Branch.objects.get(id=branch_id, is_active=True)
        unavailable_products = ProductBranchStock.objects.filter(branch=branch, is_available=False).values_list('product_id', flat=True)
        products = Product.objects.exclude(id__in=unavailable_products)  # Only show available products
        serializer = ProductDetailSerializer(products, many=True, context={'branch_id': branch_id})
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Branch.DoesNotExist:
        return Response({'error': 'Branch not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f"Error in branch_products_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def carousel_list_view(request):
    try:
        now = timezone.now()
        queryset = CarouselCard.objects.filter(status='published').select_related('carouselschedule')

        # Combine date and time into datetime ranges for accurate filtering
        queryset = queryset.filter(
            # Start condition: Either no start date/time or start is before or equal to now
            models.Q(carouselschedule__start_date__isnull=True) |
            models.Q(carouselschedule__start_date__lte=now.date()) &
            (
                models.Q(carouselschedule__start_time__isnull=True) |
                models.Q(carouselschedule__start_time__lte=now.time())
            ),
            # End condition: Either no end date/time or end is after or equal to now
            models.Q(carouselschedule__end_date__isnull=True) |
            models.Q(carouselschedule__end_date__gte=now.date()) &
            (
                models.Q(carouselschedule__end_time__isnull=True) |
                models.Q(carouselschedule__end_time__gte=now.time()) |
                models.Q(carouselschedule__end_date__gt=now.date())  # Key fix: Allow if end_date is in the future
            )
        )
        serializer = CarouselCardSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        print(f"Error in carousel_list_view: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    finally:
         close_old_connections()