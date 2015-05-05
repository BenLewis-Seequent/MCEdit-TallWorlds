============
Cubic Chunks
============

Cubic chunks are different to normal chunks as not all chunks in a column
needs to be loaded at once. Also entities are actually part of the chunk
instead of the column although in tall worlds entities can also be stored
in the column.


Implementation
^^^^^^^^^^^^^^

The proposed implementation is a hybrid between A column being a whole chunk
and being a partial chunk.

There will be control over specific 3d chunks but the ability to reference
chunks in 2d that then will load the required sub chunks as needed.

=============
Compatibility
=============

Part of the goal of this fork is to be compatible with MCEdit filters
so that migrating them is easy.

All methods that end in _cc will be there for compatibility reasons.

===========
File Format
===========

Tall Worlds mod save its chunks to a MapDB database. MapDB is a java
library for saving java collections. The file format is complicated
so will be hard to implement in python.

So for at least the prototype i have decided to create a java library
that reads the data and sends it via socket to mcedit.

