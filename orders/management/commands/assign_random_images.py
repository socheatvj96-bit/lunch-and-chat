from django.core.management.base import BaseCommand
from orders.models import MenuItem, MenuItemImage
from django.core.files import File
from django.conf import settings
import os
import random
import shutil

class Command(BaseCommand):
    help = 'Assigns random images to menu items that do not have any images'

    def handle(self, *args, **options):
        # Path to source images
        source_dir = os.path.join(settings.BASE_DIR, 'orders', 'pics_for_design_fantasy')
        
        if not os.path.exists(source_dir):
            self.stdout.write(self.style.ERROR(f'Source directory not found: {source_dir}'))
            return

        # Get all images from source directory
        source_images = [f for f in os.listdir(source_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
        
        if not source_images:
            self.stdout.write(self.style.ERROR('No images found in source directory'))
            return

        self.stdout.write(f'Found {len(source_images)} images')

        # Get items without images
        items = MenuItem.objects.all()
        updated_count = 0

        for item in items:
            if item.images.exists():
                continue

            # Select random image
            image_name = random.choice(source_images)
            source_path = os.path.join(source_dir, image_name)
            
            self.stdout.write(f'Assigning {image_name} to {item.name}')
            
            try:
                with open(source_path, 'rb') as f:
                    # Create MenuItemImage
                    menu_item_image = MenuItemImage(
                        menu_item=item,
                        is_primary=True,
                        order=0
                    )
                    # Save image file
                    menu_item_image.image.save(image_name, File(f), save=True)
                    updated_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error assigning image to {item.name}: {e}'))

        self.stdout.write(self.style.SUCCESS(f'Successfully assigned images to {updated_count} items'))
