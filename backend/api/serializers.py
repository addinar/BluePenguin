from django.contrib.auth.models import User
from rest_framework import serializers
from .models import *
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.urls import reverse
from .utils import *
from django.conf import settings
from supabase import create_client
from django.db import transaction

from django.utils import timezone

'''
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "password"]
        extra_kwargs = {"password": {"write_only": True}} # tells django we want to accept password when creating new user, but not return password when giving info about user

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data) # ** splitting up keyword arguments and passing such as dictionary
        return user
    

class NoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Note
        fields = ["id", "title", "content", "created_at", "author"]
        extra_kwargs = {"author": {"read_only": True}} # we only read who the author is, not write
'''

class CardDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CardDetails
        fields = ["id", "card_number", "card_holder_name", "expire_month", "expire_year", "cvv"]
    
    def create(self, validated_data):
        return CardDetails.objects.create(**validated_data)
    
    def update(self, instance, validated_data):
        card_details_data = validated_data.pop("card_details", None)
        if card_details_data:
            card_details = instance.card_details
            for attr in ['card_number', 'card_holder_name', 'expire_month', 'expire_year', 'cvv']:
                if attr in card_details_data:
                    setattr(card_details, attr, card_details_data[attr])
            card_details.save()
        return instance


class PayPalDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayPalDetails
        fields = ["id", "paypal_email"]
    
    def create(self, validated_data):
        return PayPalDetails.objects.create(**validated_data)
    
    def update(self, instance, validated_data):
        paypal_details_data = validated_data.pop("paypal_details", None)
        if paypal_details_data:
            paypal_details = instance.paypal_details
            for attr in ['paypal_email']:
                if attr in paypal_details_data:
                    setattr(paypal_details, attr, paypal_details_data[attr])
            paypal_details.save()
        return instance

class ShippingAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingAddress
        fields = ["id", "street_address", "address_line_2", "city", "state", "zip", "country"]
    
    def create(self, validated_data):
        return ShippingAddress.objects.create(**validated_data)
    
    def update(self, instance, validated_data):
        # Remove the nesting and directly update fields
        for attr in ['street_address', 'address_line_2', 'city', 'state', 'zip', 'country']:
            if attr in validated_data:
                setattr(instance, attr, validated_data[attr])
        instance.save()
        return instance 


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=20)
    email = serializers.EmailField()
    password = serializers.CharField(max_length=20, write_only=True)
    first_name = serializers.CharField()
    last_name = serializers.CharField()

    def create(self, validated_data):
        supabase_user = None
        try:
            # First create Supabase user
            supabase = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_ROLE_KEY,
            )

            print("Creating Supabase user...")
            supabase_response = supabase.auth.admin.create_user({
                'email': validated_data['email'],
                'password': validated_data['password'],
                'email_confirm': True
            })
            # Convert generator to user data
            supabase_user = next(iter(supabase_response))
            print(f"Supabase user created: {supabase_user}")

            # Use transaction to ensure all Django models are created or none
            with transaction.atomic():
                print("Creating Django user...")
                user = User.objects.create_user(
                    username=validated_data["username"],
                    email=validated_data["email"],
                    password=validated_data["password"],  # create_user handles password hashing
                    first_name=validated_data["first_name"],
                    last_name=validated_data["last_name"]
                )
                print(f"Django user created: {user}")

                print("Creating Account and Profile...")
                account = Account.objects.create(user=user)
                
                display_name = f"{validated_data['first_name']} {validated_data['last_name']}"
                profile = Profile.objects.create(
                    account=account,
                    display_name=display_name,
                    description=""
                )
                print("Account and Profile created")

                return user

        except Exception as e:
            print(f"Error occurred: {str(e)}")
            if supabase_user:
                try:
                    print("Attempting to delete Supabase user...")
                    supabase.auth.admin.delete_user(supabase_user.user.id)  # Access the ID correctly
                    print("Supabase user deleted")
                except Exception as cleanup_error:
                    print(f"Failed to delete Supabase user: {str(cleanup_error)}")
            raise serializers.ValidationError(f"Failed to create user: {str(e)}")

    

class AccountSerializer(serializers.ModelSerializer):
    # the following fields are not in the Account model, but in the User model
    username = serializers.CharField(source="user.username", max_length=20)
    password = serializers.CharField(max_length=20, write_only=True)
    email = serializers.EmailField(source="user.email")
    first_name = serializers.CharField(source="user.first_name")
    last_name = serializers.CharField(source="user.last_name")
    # Note: source = user.xyz tells Django to look for xyz in the User model not Account

    class Meta:
        model = Account
        fields = ["id", "first_name", "last_name", "username", "status", "email", "balance", "password"]
        extra_kwargs = {
            "status": {"read_only":True}, 
            "balance": {"read_only": True}, 
            "password": {"write_only": True}
        }
    
    def update(self, instance, validated_data):
        # extract the data from User model
        user_data = validated_data.pop('user', {})
        password = user_data.pop("password", None)
        # update password separately since it's hashed
        user = instance.user # here, user is the instance of the User model
        if password:
            user.set_password(password)

        # update account settings
        for attr in ['first_name', 'last_name', 'username', 'email']:
            if attr in user_data:
                setattr(instance.user, attr, user_data[attr])
        
        # save everything
        user.save()
        instance.save()

        return instance
    
# sign in serializer - uses tokens
class SignInSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField() 

# next do a profile serializer for the account
class ProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="account.user.username")
    slug = serializers.SlugField(source="account.user.username", read_only=True)
    display_icon = serializers.ImageField(required=False)
    average_rating = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ['id', 'display_name', 'display_icon', 'description', 'average_rating', 'username', 'slug', 'status']
        extra_kwargs = {
            "average_rating": {"read_only": True},
            "username": {"read_only": True},
            "status": {"read_only": True},
        }
    
    # you can edit display name, display icon, and description
    def update(self, instance, validated_data):
        for attr in ['display_name', 'display_icon', 'description']:
            if attr in validated_data:
                if attr == 'display_icon':
                    display_icon = validated_data['display_icon']
                    destination_blob_name = f"profile_pics/{instance.account.user.username}/{display_icon.name}"
                    url = upload_to_gcs(display_icon, destination_blob_name)
                    setattr(instance, attr, url)
                else:
                 setattr(instance, attr, validated_data[attr])
                # setattr(object, name, value)
                # object - object whose attribute is to be set
                # name - attribute name as string
                # value - value to set for the attribute
                # e.g. setattr(obj, 'x', 123) is equivalent to obj.x = 123
        
        instance.save()
        return instance
    
    def get_average_rating(self, obj):
        return obj.average_rating
    
    def get_status(self, obj):
        if obj.account.status == STATUS_USER:
            return 'USER'
        elif obj.account.status == STATUS_VIP:
            return 'VIP'
        elif obj.account.status == STATUS_VISITOR:
            return 'VISITOR'


class RatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rating
        fields = ["rating", "rater", "ratee"]
        extra_kwargs = {
            "rater": {"read_only": True},
            "ratee": {"read_only": True}
        }
    
    def create(self, validated_data):
        rater_user = self.context['request'].user # the user handling the request
        rater = rater_user.account.profile

        validated_data['rater'] = rater

        return Rating.objects.create(**validated_data)
    

class ItemSerializer(serializers.ModelSerializer):
    username = serializers.CharField(required=False, source="profile.account.user.username")
    display_icon = serializers.ImageField(required=False, source="profile.display_icon")
    image_urls = serializers.ListField(write_only=True, required=False)

    class Meta:
        model = Item
        fields = ['id', 'title', 'username', 'display_icon', 'description', 'deadline', 'collection', 'image_urls', 'selling_price', 'profile', 'maximum_bid', 'minimum_bid']
        extra_kwargs = {
            "username": {"read_only": True},
            "display_icon": {"read_only": True}
        }

    def create(self, validated_data):
        # Remove extra fields before creating the item
        validated_data.pop('username', None)
        validated_data.pop('display_icon', None)
        title = validated_data.pop("title")
        user = self.context['request'].user # the current user handling the request
        profile = user.account.profile
        files = validated_data.pop('images', [])
        validated_data['profile'] = profile

        description = validated_data.pop("description")
        deadline = validated_data.pop("deadline")
        collection = validated_data.pop("collection")
        selling_price = validated_data.pop("selling_price")

        item = Item.objects.create(title=title, profile=profile, description=description, deadline=deadline, collection=collection, selling_price=selling_price)

        gcs_urls = []
        for file in files:
            folder_name = item.title.lower().replace(" ", "")
            destination_blob_name = f"items/{folder_name}/{file.name}"
            url = upload_to_gcs(file, destination_blob_name)
            gcs_urls.append(url)
        
        item.image_urls = gcs_urls
        item.save()

        return item
    

class CommentSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="profile.account.user.username")
    display_icon = serializers.ImageField(source="profile.display_icon")
    likes = serializers.SerializerMethodField()
    dislikes = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ['id', 'item', 'text', 'profile', 'parent', 'children', 'time_of_comment', 'username', 'display_icon', 'likes', 'dislikes']
        extra_kwargs = {
            "item": {"read_only": True},
            "profile": {"read_only": True},
            "parent": {"read_only": True},
            "time_of_comment": {"read_only": True},
        }
    
    # create a comment
    def create(self, validated_data):
        # item = self.context['request'].item - why cant you put this here in the serializer?
        # self.context of a serializer is passed in from the view, including info about the request object
        # for self.context['request'].item, DRF does not automatically add the item attribute to the request object.
        
        # *** the request object contains standard fields like request.user, request.method, and request.data
        # to pass in item, it must be from the view where this is being handled. 
        item = self.context['item'] # this assumes that 'item' is being passed in via the context from the view
        parent = self.context['parent']
        user = self.context['request'].user
        profile = user.account.profile

        validated_data['item'] = item
        validated_data['profile'] = profile
        validated_data['parent'] = parent

        comment = Comment.objects.create(**validated_data)

        item_user = item.profile.account.user
        text = validated_data['text']
        item_user.email_user("New Comment for You", f"{user.username} commented: {text}", from_email=settings.EMAIL_HOST_USER)

        return comment
    
    # get its children
    def get_children(self, obj):
        children = obj.children.all()
        return CommentSerializer(children, many=True).data
    
    def get_likes(self, obj):
        return obj.likes
    
    def get_dislikes(self, obj):
        return obj.dislikes
    

class SaveSerializer(serializers.ModelSerializer):
    image_urls = serializers.JSONField(source='item.image_urls')
    title = serializers.CharField(source='item.title')
    current_bid = serializers.DecimalField(source='item.highest_bid', max_digits=6, decimal_places=2)

    class Meta:
        model = Save
        fields = ['id', 'item', 'profile', 'time_saved', 'image_urls', 'title', 'current_bid']
        extra_kwargs = {
            "item": {"read_only": True},
            "profile": {"read_only": True},
            "image": {"read_only": True},
            "title": {"read_only": True},
            "current_bid": {"read_only": True},
            "time_saved": {"read_only": True},
        }

    def create(self, validated_data):
        item = self.context['item']
        user = self.context['request'].user
        profile = user.account.profile

        validated_data['item'] = item
        validated_data['profile'] = profile

        save = Save.objects.create(**validated_data)

        return save

class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = ['id', 'reporter', 'reportee', 'report']
        extra_kwargs = {
            "reporter": {"read_only": True},
            "reportee": {"read_only": True},
        }
    
    def create(self, validated_data):
        reporter_user = self.context['request'].user
        reporter = reporter_user.account.profile

        validated_data['reporter'] = reporter

        report = Report.objects.create(**validated_data)

        return report

class LikeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Like
        fields = ['id', 'profile', 'comment']
        extra_kwargs = {
            'profile': {'read_only': True},
            'comment': {'read_only': True},
        }

    def create(self, validated_data):
        user = self.context['request'].user
        profile = user.account.profile
        comment = self.context['comment']

        like = Like.objects.create(profile=profile, comment=comment)

        comment_user = comment.profile.account.user
        comment_user.email_user('New Like on Your Comment', f'{user.username} has liked your comment: {comment.text}')

        return like
    
class DislikeSerializer(serializers.ModelSerializer):
    class Meta: 
        model = Dislike
        fields = ['id', 'profile', 'comment']
        extra_kwargs = {
            'profile': {'read_only': True},
            'comment': {'read_only': True},
        }

    
class BidSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bid
        fields = ['id', 'bid_price', 'item', 'time_of_bid', 'status', 'profile']
        extra_kwargs = {
            'item': {'read_only': True},
            'profile': {'read_only': True},
            'time_of_bid': {'read_only': True},
            'status': {'read_only': True},
        }

    def create(self, validated_data):
        user = self.context['request'].user
        item = self.context['item']
        profile = user.account.profile

        bid_price = validated_data['bid_price']
        status = NOT_HIGHEST_CHOICE
        validated_data['status'] = status

        bid = Bid.objects.create(
            profile=profile,
            item=item,
            bid_price=bid_price,
            time_of_bid=timezone.now(),
            status=status
        )

        return bid
    
class TransactionSerializer(serializers.ModelSerializer):
    seller_username = serializers.CharField(source='seller.user.username', read_only=True)
    buyer_username = serializers.CharField(source='buyer.user.username', read_only=True)
    item_title = serializers.CharField(source='bid.item.title', read_only=True)
    bid_amount = serializers.DecimalField(source='bid.bid_price', max_digits=6, decimal_places=2, read_only=True)
    image_urls = serializers.JSONField(source='bid.item.image_urls')
    bid = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Transaction
        fields = ['id', 'seller_username', 'buyer_username', 'bid', 'item_title', 'bid_amount', 'status', 'estimated_delivery', 'carrier', 'shipping_cost', 'image_urls']
        extra_kwargs = {
            'status': {'read_only': True},  
            'estimated_delivery': {'read_only': True}, 
            'carrier': {'read_only': True},
            'shipping_cost': {'read_only': True},
        }

class ParcelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parcel
        fields = ['id', 'item', 'length', 'width', 'height', 'weight', 'distance_unit', 'weight_unit']
        extra_kwargs = {
            "item": {"read_only": True}
        }


    def create(self, validated_data):
        transaction = self.context['transaction']
        validated_data['transaction'] = transaction
        parcel = Parcel.objects.create(**validated_data)
        return parcel 
    
class QuitRequestSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='account.user.username', read_only=True)
    email = serializers.CharField(source='account.user.email', read_only=True)
    class Meta:
        model = QuitRequest
        fields = ['id', 'username', 'email', 'reason', 'status']
        extra_kwargs = {
            "username": {"read_only": True},
            "email": {"read_only": True},
            "status": {"read_only": True},
        }

    def create(self, validated_data):
        username = self.context['username']
        email = self.context['email']
        reason = self.context['reason']

        validated_data['username'] = username
        validated_data['email'] = email
        validated_data['reason'] = reason

        quitrequest = QuitRequest.objects.create(**validated_data)

        return quitrequest