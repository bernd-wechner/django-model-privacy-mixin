# Django Model Privacy MixIn

[Django](https://www.djangoproject.com/) is one of the most popular Python web frameworks today. Importantly it provides an [ORM](https://en.wikipedia.org/wiki/Object%E2%80%93relational_mapping) permitting us to define models as Python classes that Django maps to a databse representations for us. 

A common need on-line today is to maintain privacy of user data. Such privacy needs to be managed across any website that stores user information, at every level possible. We are all tired of reading about data breaches that sees some hack suck all the users, account names, full names and email adresses and whatever else from some insecure database.

This Django model MixIn works at one level, a rather low one in the Django framework, to securely deny access to private data to the wrong people.

To use it, simply mix it in to your model defintion. Consider the basic Django example of:

The basic Django example of model:

```python
from django.db import models

class Person(models.Model):
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
```

can be extended thusly:

```python
from django.db import models
from django_model_privacy_mixin import PrivacyMixIn

class Person(PrivacyMixIn, models.Model):
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
```

Of course that is not enough, you've now pixed it in, but haven't told ther Privacy MixIn what is and what isn't private and to whome. For that we simply define a `visibility_field` field for any field we wish to make private. This is expected to be a Django [BitField](https://pypi.org/project/django-bitfield/). Further you will need users and accounts privacy management meaningful (otherwise you only have dispalyed and not displayed and don't need the complexity of this or any other MixIn).

The first step is to define a set of permissions or visibility scopes. This is the example straight out of BitField documentation:

```Python
class MyModel(models.Model):
    flags = BitField(flags=(
        ('awesome_flag', 'Awesome Flag!'),
        ('flaggy_foo', 'Flaggy Foo'),
        ('baz_bar', 'Baz (bar)'),
    ))
```

This MixIn uses such a set of flags as visibility rules. So it is prudent to separate the defintions:

```Python
class MyModel(models.Model):
    x = models.CharField(max_length=30)
    y = models.CharField(max_length=30)
    z = models.CharField(max_length=30)
    
    rules = (
        ('rule_1', 'Everyone'),
        ('rule_2', 'Group Members'),
        ('rule_3', 'Staff')
    )
    
    visibility__x = BitField(rules)
    visibility__y = BitField(rules)
    visibility__z = BitField(rules)    
```

The fields and rules though need to folow a naming convention so that the MixIn can interpret them. The convensions are as follows:

### Fields

A BitField that have the the same name as another field in the model with `visibility_` as a prefix, defines the visibility rules for that field. That is `visibility__x = BitField(rules)` defines the rules for `x`. Fields that don't have a matching `visibility_` BitField won't be managed by this MixIn. They will be left alone.

### Rules

BtiField accepts a list of tuples of the form `(flag, label)`.  This MixIn acts only on flags that are named as follows:

`all` - if this flag is set the target field is visible to all. 

`all_*` - where `*` is the name of field on the `auth.User` instance (of an authroised user) or its extensions (models with a `OneToOneField` rlation to `auth.User`). For example `all_is_staff`. If this flag is set then the target field is visible only if the the user has an `is_staff` field that is True otherwise it is hidden. These attributes can be on User [extensions](https://docs.djangoproject.com/en/3.2/topics/auth/customizing/#extending-the-existing-user-model) too. 

`all_not_*` - same as `all_*` just its inverse. Will hide the target field if the `*` field evaluates to True.

`share_*` - if this flag is set, the target field will be visible only to users who share membership of a group defined by the `*` attribute on a an `auth.User` instance  (of an authroised user) or its extensions (as with `all_*`). Where `all_*` provides visibility to all users who have a True `*` attribute, `share_*` expects the `*` attribute to be a [ManyToManyField](https://docs.djangoproject.com/en/3.2/ref/models/fields/#manytomanyfield) and tests if the authorsed User and the owner of the record in question are both in that group (are both members of the set the Many2ManyField defines). For this we need to know the owner of a record.

### Owners

The `share_*` rule needs to know if the owner of the record being fetched from the database and the user requesting the record share membership in the group `*`. For that it needs to know who owns the record. This must be indicated to the MixIn by providing an `owner` property. For example:

```Python
from django.db import models
from django.contrib.auth.models import User
from django_model_privacy_mixin import PrivacyMixIn

class Person(PrivacyMixIn, models.Model):
	user = models.OneToOneField(User, verbose_name='Username')
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)

    @property
    def owner(self) -> User:
        return self.user
```

`owner` can of course be a field too, but it's much easier to add a property to any model you wish to add the `PrivacyMixIn` to.

Putting that all together in a rich example, here's one of a `Player` model in which players can be in teams and leagues and where they can be registrars as well (umpires, referees, or such):

```Python
from django.db import models
from django.contrib.auth.models import User
from django_model_privacy_mixin import PrivacyMixIn

class Player(PrivacyMixIn, models.Model):
    # Player fields
    nickname = models.CharField('Nickname', max_length=MAX_NAME_LENGTH, unique=True)
    personal = models.CharField('Personal Name', max_length=MAX_NAME_LENGTH)
    family = models.CharField('Family Name', max_length=MAX_NAME_LENGTH)
    email = models.EmailField('Email Address', blank=True, null=True)
    is_registrar = models.BooleanField('Authorised to record session results?', default=False)

    # Membership fields
    teams = models.ManyToManyField('Team', related_name='players_in_team') 
    leagues = models.ManyToManyField('League', related_name='players_in_league')

    # account
    user = models.OneToOneField(User, related_name='player')

    # Privacy control (interfaces with django_model_privacy_mixin)
    visibility = (
        ('all', 'Everyone'),
        ('share_leagues', 'League Members'),
        ('share_teams', 'Team Members'),
        ('all_is_registrar', 'Registrars'),
        ('all_is_staff', 'Staff')
    )

    visibility_nickname = BitField(visibility, default=('all',))
    visibility_personal = BitField(visibility, default=('all',))
    visibility_family = BitField(visibility, default=('share_leagues', 'all_is_staff'))
    visibility_email = BitField(visibility, default=('share_leagues', 'share_teams'))

    @property
    def owner(self) -> User:
        return self.user
```

And voila, anyone accessing instances of Player will see the `nickname` and `personal`, but if they are not staff (`is_staff` is True on their `user`) or share a league with `owner` the `family` name will be replaced by `PrivacyMixIn.HIDDEN` (which you cna configure but defaults to `<Hidden>` - which BTW won't display unless you [mark it safe](https://docs.djangoproject.com/en/3.2/ref/utils/#django.utils.safestring.mark_safe)).

### Configuration

PrivacyMixIn has only two configurations:

`PrivacyMixIn.HIDDEN` - which is a string that is returned in place of the content of any hidden field.

`PrivacyMixIn.HIDE_EMPTY_FIELD`- If `True` empty fields are also replaced by `PrivacyMixIn.HIDDEN` when visibility is denied. Defaults to False. Empty fields are just returned as they are.

### The Internals

This isn't a big MixIn, it's all in `__init__.py`. But to be clear the mixin overrides the model's `from_db`method, calling the original method then testing the visibility rules, making and substitutes needed and returning the result. Importantly	

### Forms - [DANGER Will Robinson DANGER](https://www.youtube.com/watch?v=RG0ochx16Dg)

A side effect of simply replacing fields is that if a user has the right to edit the obect and save it, then they will see some with the content `PrivacyMixIn.HIDDEN`. If they save that of course you're letting people from whome data is hidden overwrite it in the database! Big NO NO. 

The MixIn thus provides on the model instances a method `fields_for_model()`. There are a number of ways you can create forms in Django of course and so it's up to you restrict users form views to the filtered `fields_for_model()`. To illustrat one simple example we take from the documentation for the standard [UpdateView](https://docs.djangoproject.com/en/3.2/ref/class-based-views/generic-editing/#updateview):

```Python
from django.views.generic.edit import UpdateView
from myapp.models import Author

class AuthorUpdateView(UpdateView):
    model = Author
    fields = ['name']
    template_name_suffix = '_update_form'
```

and tailor it the Player example above while overriding [`get_object()`](https://docs.djangoproject.com/en/3.2/ref/class-based-views/mixins-single-object/#django.views.generic.detail.SingleObjectMixin.get_object):

```Python
from django.views.generic.edit import UpdateView
from django.forms.models import fields_for_model
from django.shortcuts import get_object_or_404
from myapp.models import Player

class PlayerUpdateView(UpdateView):
    model = Player
    
    def get_object(self, *args, **kwargs):
        self.pk = self.kwargs['pk']
        self.obj = get_object_or_404(self.model, pk=self.kwargs['pk'])

        if callable(getattr(self.obj, 'fields_for_model', None)):
            # Call the PrivacyMixIn's fields_for_model()
            self.fields = self.obj.fields_for_model()
        else:
            # Call the Django's fields_for_model()
            self.fields = fields_for_model(self.model)

        return self.obj
```

Now that will present to a user a form to edit a record which is missing the fields that are hidden, that they have no right to see or alter.

Of course there are various ways of rendering forms in Django and you're responsible for ensuring they only show the fields that the PrivacyMixIn says (in `obj.fields_for_model()`) should be shown, it can't predict all the ways you present forms to users.
