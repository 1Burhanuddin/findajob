-- strip-bookmarks.lua
-- Clears heading identifiers so pandoc does not emit <w:bookmarkStart> elements
-- in .docx output. Eliminates the blue bookmark icons that appear in Word when
-- "Show bookmarks" is enabled (Word → Options → Advanced → Show document content).
function Header(el)
  el.identifier = ""
  return el
end
