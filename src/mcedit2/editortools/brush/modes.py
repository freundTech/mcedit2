"""
    modes
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import logging
from PySide import QtGui, QtCore
from mcedit2.editortools.brush.masklevel import MaskLevel
from mcedit2.util.showprogress import showProgress
from mcedit2.widgets.blockpicker import BlockTypeButton
from mcedit2.widgets.layout import Column, Row
from mceditlib.anvil.biome_types import BiomeTypes
from mceditlib.geometry import Vector
from mceditlib.selection import BoundingBox

log = logging.getLogger(__name__)


class BrushMode(QtCore.QObject):
    optionsWidget = None

    def __init__(self, brushTool):
        super(BrushMode, self).__init__()
        self.brushTool = brushTool

    def brushBoundingBox(self, center, options=None):
        # Return a box of size options['brushSize'] centered around point.
        # also used to position the preview cursor
        options = options or {}
        size = options['brushSize']
        x, y, z = size
        origin = Vector(*center) - (Vector(x, y, z) / 2) + Vector((x % 2) * 0.5, (y % 2) * 0.5, (z % 2) * 0.5)
        return BoundingBox(origin, size)

    def brushBoxForPoint(self, point, options):
        return self.brushBoundingBox(point, options)

    def applyToPoint(self, command, point):
        """
        Called by BrushCommand for brush modes that can't be implemented using applyToChunk
        :type point: Vector
        :type command: BrushCommand
        """
        raise NotImplementedError

    def applyToSelection(self, command, selection):
        """
        Called by BrushCommand to apply this brush mode to the given selection. Selection
        is generated by calling BrushShape.createShapedSelection and optionally
        combining multiple selections.

        Return a progress iterator.

        Parameters
        ----------

        command: BrushCommand
        selection: SelectionBox

        Returns
        -------
        progress: Iterable
        """
        raise NotImplementedError

    def createCursorLevel(self, brushTool):
        """
        Called by BrushTool to create a MaskLevel (or WorldEditorDimension?) to use for the cursor.
        Should return a world with a bounding box sized to `brushTool.options['brushSize']` and
        centered at 0, 0, 0 (???)

        :param brushTool:
        :return:
        """
        return None


class Fill(BrushMode):
    name = "fill"

    def __init__(self, brushTool):
        super(Fill, self).__init__(brushTool)
        self.displayName = self.tr("Fill")

        self.optionsWidget = QtGui.QWidget()
        label = QtGui.QLabel(self.tr("Fill Block:"))
        self.blockTypeButton = BlockTypeButton()
        self.blockTypeButton.editorSession = brushTool.editorSession
        self.blockTypeButton.block = brushTool.editorSession.worldEditor.blocktypes['minecraft:stone']
        self.blockTypeButton.blocksChanged.connect(brushTool.updateCursor)

        self.optionsWidget.setLayout(Column(
            Row(label, self.blockTypeButton, margin=0),
            None, margin=0))

    def getOptions(self):
        return {'blockInfo': self.blockTypeButton.block}

    def applyToSelection(self, command, selection):
        """

        :type command: BrushCommand
        """
        return command.editorSession.currentDimension.fillBlocksIter(selection, command.options['blockInfo'])

    def createCursorLevel(self, brushTool):
        box = self.brushBoxForPoint((0, 0, 0), brushTool.options)
        selection = brushTool.brushShape.createShapedSelection(box,
                                                               brushTool.editorSession.currentDimension)
        cursorLevel = MaskLevel(selection,
                                self.blockTypeButton.block,
                                brushTool.editorSession.worldEditor.blocktypes)
        return cursorLevel


class Replace(BrushMode):
    name = 'replace'

    def __init__(self, brushTool):
        super(Replace, self).__init__(brushTool)
        self.displayName = self.tr("Replace")

    def applyToSelection(self, command, selection):
        pass


class Biome(BrushMode):
    name = "biome"

    def __init__(self, brushTool):
        super(Biome, self).__init__(brushTool)
        self.displayName = self.tr("Biome")

        self.optionsWidget = QtGui.QWidget()
        label = QtGui.QLabel(self.tr("Fill Biome:"))
        self.biomeTypeBox = QtGui.QComboBox()
        self.biomeTypes = BiomeTypes()
        for biome in self.biomeTypes.types.values():
            self.biomeTypeBox.addItem(biome.name, biome.ID)

        self.biomeTypeBox.activated.connect(brushTool.updateCursor)
        self.optionsWidget.setLayout(Column(Row(label, self.biomeTypeBox, margin=0), None, margin=0))

    def getOptions(self):
        return {'biomeID': self.biomeTypeBox.itemData(self.biomeTypeBox.currentIndex())}

    def applyToSelection(self, command, selection):
        biomeID = command.options['biomeID']
        dim = command.editorSession.currentDimension
        count = selection.chunkCount
        for i, (cx, cz) in enumerate(selection.chunkPositions()):
            yield i, count, "Applying biome brush"

            if not dim.containsChunk(cx, cz):
                continue

            chunk = dim.getChunk(cx, cz)
            touched = False
            mask = None
            for cy in selection.sectionPositions(cx, cz):
                section = chunk.getSection(cy)
                if section is None:
                    continue

                touched = True
                sectionMask = selection.section_mask(cx, cy, cz)

                # collapse by column
                sectionMask = sectionMask.any(0)

                if mask is None:
                    mask = sectionMask
                else:
                    mask |= sectionMask

            if touched:
                z, x = mask.nonzero()
                chunk.Biomes[z, x] = biomeID

                chunk.dirty = touched

    def brushBoxForPoint(self, point, options):
        x, y, z = options['brushSize']
        options['brushSize'] = x, 1, z

        return self.brushBoundingBox(point, options)

    def createCursorLevel(self, brushTool):
        box = self.brushBoxForPoint((0, 0, 0), brushTool.options)
        selection = brushTool.brushShape.createShapedSelection(box, brushTool.editorSession.currentDimension)

        cursorLevel = MaskLevel(selection,
                                brushTool.editorSession.worldEditor.blocktypes["minecraft:grass"],
                                brushTool.editorSession.worldEditor.blocktypes,
                                biomeID=self.getOptions()['biomeID'])
        return cursorLevel


BrushModeClasses = [Fill, Replace, Biome]
