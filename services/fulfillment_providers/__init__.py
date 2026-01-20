from abc import ABC, abstractmethod

class FulfillmentProvider(ABC):
    """
    Abstract base class for fulfillment providers.
    """
    
    @abstractmethod
    def submit_order(self, order_id: int, shipping_data: dict, pdf_path: str) -> str:
        """
        Submit an order to the provider.
        
        Args:
            order_id (int): The local order ID.
            shipping_data (dict): Shipping details (name, address, etc).
            pdf_path (str): Path or URL to the print-ready PDF.
            
        Returns:
            str: The provider's job ID or reference ID.
        """
        pass

    @abstractmethod
    def cancel_order(self, provider_job_id: str) -> bool:
        """
        Cancel an order with the provider.
        """
        pass
        
    @abstractmethod
    def get_status(self, provider_job_id: str) -> dict:
        """
        Get the status of an order.
        """
        pass
