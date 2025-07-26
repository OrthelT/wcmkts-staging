from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class MarketOrder(Base):
    __tablename__ = 'marketOrders'
    order_id = Column(Integer, primary_key=True)
    is_buy_order = Column(Boolean)
    type_id = Column(Integer)
    duration = Column(Integer)
    issued = Column(DateTime)
    price = Column(Float)
    volume_remain = Column(Integer)

class InvType(Base):
    __tablename__ = 'invTypes'
    typeID = Column(Integer, primary_key=True)
    groupID = Column(Integer)
    typeName = Column(String)
    description = Column(String)
    mass = Column(Float)
    volume = Column(Float)
    capacity = Column(Float)
    portionSize = Column(Integer)
    raceID = Column(Integer)
    basePrice = Column(Float)
    published = Column(Boolean)
    marketGroupID = Column(Integer)
    iconID = Column(Integer)
    soundID = Column(Integer)
    graphicID = Column(Integer)




if __name__ == "__main__":
    pass