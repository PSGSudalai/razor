from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import Http404, HttpResponse, JsonResponse, FileResponse
from django.template.loader import get_template
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import razorpay
import json
from django.conf import settings
import os
import pdfkit
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from .models import Cart, Products, Order
from .form import AddProduct
from weasyprint import HTML
from datetime import datetime
# import pdfkit


def get_razorpay_client():
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_SECRET_KEY))

def generate_pdf(order):
    # Path to save the PDF
    pdf_path = f"order_{order.order_id}.pdf"
    full_pdf_path = os.path.join(settings.MEDIA_ROOT, pdf_path)  # Save to media directory

    # HTML content
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .header {{ font-weight: bold; font-size: 14pt; text-align:center; }}
            .details {{ font-size: 12pt; }}
        </style>
    </head>
    <body>
        <div class="header">Shopping market</div>
        <div class="details">
            <p>User: {{request.user.username}}</p>
            <p>Address: xyz,chennai</p>
            <p>GST Number: 12547896340</p>
            <p>PAN Number: PDDS286S</p>
            <p>Order ID: {order.order_id}</p>
            <p>Total Amount: ₹{order.total_amount}</p>
            <p>Date: {datetime.now().strftime('%Y-%m-%d')}</p>
        </div>
    </body>
    </html>
    """
    # # Generate PDF
    # pdfkit.from_string(html_content, full_pdf_path)

    HTML(string=html_content).write_pdf(full_pdf_path)

    return pdf_path

def download_receipt(request, order_id):
    pdf=pdfkit.from_url(request.build_absolute_url(reverse('cart-view'),False,order_id=order_id))
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="receipt_{order_id}.pdf"'
    return response
def register(request):
    if request.method == 'POST':
        firstname = request.POST.get('firstname')
        lastname = request.POST.get('lastname')
        username = request.POST.get('username')
        email = request.POST.get('email')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists. Please choose another username.')
        elif User.objects.filter(email=email).exists():
            messages.error(request, 'Email address is already in use. Please use another email.')
        elif password1 != password2:
            messages.error(request, 'Passwords do not match. Please try again.')
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password1,
                first_name=firstname,
                last_name=lastname
            )
            user.save()
            login(request, user)
            messages.success(request, 'Registration successful')
            return redirect('home')
    return render(request, 'register.html')

def Signin(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("home")
        else:
            messages.error(request, "Invalid Username or Password")
            return redirect('signin')
    return render(request, 'login.html')

def Signout(request):
    logout(request)
    return redirect('home')

def home(request):
    items = Products.objects.all()
    cart_count=0
    if request.user:
        cart_count = Cart.objects.filter(user=request.user).count()
    return render(request, 'home.html', {'items': items, 'count': cart_count})


@login_required(login_url='signin')
def item(request):
    if request.method == 'POST':
        form = AddProduct(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request,'Product created successfully!')
            return redirect('home')
    else:
        form = AddProduct()
    context = {'form': form}
    return render(request, 'item_cart.html', context)

@login_required(login_url='signin')

def cart(request, pk):
    cart_item = get_object_or_404(Products, id=pk)
    user = request.user
    quantity = int(request.POST.get('quantity', 1))
    price = cart_item.price
    total = price * quantity  # Calculate total price based on quantity

    try:
        cart_product = Cart.objects.get(product=cart_item, user=user)
        cart_product.quantity += quantity
        cart_product.total = cart_product.price * cart_product.quantity
        cart_product.save()
        messages.success(request, f'Updated {cart_item.item} quantity to {cart_product.quantity}.')
    except Cart.DoesNotExist:
        Cart.objects.create(product=cart_item, user=user, price=price, quantity=quantity, total=total)
        messages.success(request, f'Added {cart_item.item} to your cart.')

    return redirect('home')

def delete(request, pk):
    cart = Cart.objects.get(id=pk)
    cart.delete()
    return redirect('cart-view')

def back(request):
    return redirect('home')

@login_required(login_url='signin')
def cart_view(request):
    cart_items = Cart.objects.filter(user=request.user)
    cart_total = 0
    for i in cart_items:
        cart_total += i.total
    order_id = cart_items.first().order.id 
    context = {'cart_items': cart_items, 'cart_total': cart_total, 'order_id': order_id}
    return render(request, 'cart.html', context)

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_SECRET_KEY))

@csrf_exempt
def create_order(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            amount = data.get('amount')  # Amount in paise
            currency = 'INR'

            # Create an order on Razorpay
            razorpay_order = client.order.create(dict(amount=amount, currency=currency, payment_capture='0'))

            # Save order details in your database if necessary
            order_id = razorpay_order['id']

            return JsonResponse({
                'order_id': order_id,
                'razorpay_key': settings.RAZORPAY_KEY_ID,
                'amount': amount
            })

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
def verify_payment(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            razorpay_payment_id = data['razorpay_payment_id']
            razorpay_order_id = data['razorpay_order_id']
            razorpay_signature = data['razorpay_signature']

            # Verify payment signature
            client.utility.verify_payment_signature({
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            })

            # Assume `cart` is fetched based on some logic, e.g., from session or user
            cart_items = Cart.objects.filter(user=request.user)  # Replace with your method to get the cart
            totalamt = sum(i.total for i in cart_items)

            # Save order details
            order = Order.objects.create(
                order_id=razorpay_order_id,
                total_amount=totalamt   # Convert back to rupees
            )

            # Generate PDF receipt
            pdf_path = generate_pdf(order )
            cart_items.delete()

            return redirect('cart-view')
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': 'Invalid request'}, status=400)




@require_POST
def update_quantity(request, pk):
    cart_item = get_object_or_404(Cart, id=pk)
    action = request.POST.get('action')

    if action == 'increase':
        cart_item.quantity += 1
    elif action == 'decrease' and cart_item.quantity > 1:
        cart_item.quantity -= 1
    cart_item.total = cart_item.quantity* cart_item.price
    cart_item.save()
    return redirect('cart-view')
